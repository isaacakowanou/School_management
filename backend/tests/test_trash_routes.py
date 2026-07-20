import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    AuditLog,
    Base,
    Class,
    Course,
    CourseResult,
    DeletionBatch,
    Enrollment,
    Grade,
    GradeItem,
    Parent,
    PasswordResetToken,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)
from services.trash import RECOVERABLE_MODELS


class TrashRouteTests(unittest.TestCase):
    password = "test-password-123"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.db = self.SessionLocal()
        self._seed_base()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, *, name: str, email: str, role: str) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _headers(self) -> dict[str, str]:
        response = self.client.post("/api/v1/auth/login", json={"email": self.admin_user.email, "password": self.password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _seed_base(self) -> None:
        self.admin_user = self._user(name="Admin Trash", email="admin-trash@example.test", role="admin")
        self.teacher_user = self._user(name="Trash Teacher", email="teacher-trash@example.test", role="teacher")
        self.parent_user = self._user(name="Trash Parent", email="parent-trash@example.test", role="parent")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="TRASH-TCH")
        self.parent = Parent(user=self.parent_user, phone="555-9000")
        self.school_class = Class(
            name_fr="ZZ-TEST-Trash",
            name_en="ZZ-TEST-Trash",
            school_level="college",
            stream=None,
            sort_order=1,
            school_year="2026-2027",
        )
        self.course = Course(
            name="ZZ-TEST-Trash Course",
            code="ZZ-TEST-TRASH",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
            school_class=self.school_class,
        )
        self.db.add_all([self.teacher, self.parent, self.school_class, self.course])
        self.db.commit()

    def _student_tree(self, number: str = "ZZ-TEST-STU") -> dict:
        student = Student(
            first_name="ZZ-TEST",
            last_name=number,
            school_level="college",
            student_number=number,
            school_class=self.school_class,
        )
        self.db.add(student)
        self.db.flush()
        link = StudentParent(student=student, parent=self.parent, relationship="parent")
        enrollment = Enrollment(student=student, course=self.course)
        item = GradeItem(
            course=self.course,
            title=f"Interro {number}",
            item_type="INTERRO",
            max_score=20,
            term="1er Trimestre",
        )
        self.db.add_all([link, enrollment, item])
        self.db.flush()
        grade = Grade(student=student, grade_item=item, score=17, submitted_by_teacher=self.teacher)
        result = CourseResult(
            student=student,
            course=self.course,
            term="1er Trimestre",
            average=17,
            letter_grade="A",
            scale="20",
        )
        report = ReportCard(
            student=student,
            term="1er Trimestre",
            school_year="2026-2027",
            overall_average=17,
            scale="20",
            status="approved",
        )
        self.db.add_all([grade, result, report])
        self.db.flush()
        report_course = ReportCardCourse(
            report_card=report,
            course=self.course,
            course_name=self.course.name,
            average=17,
            letter_grade="A",
        )
        self.db.add(report_course)
        self.db.commit()
        return {
            "student": student,
            "link": link,
            "enrollment": enrollment,
            "item": item,
            "grade": grade,
            "result": result,
            "report": report,
            "report_course": report_course,
        }

    def _batch_rows(
        self,
        *,
        entity_type: str,
        entity_id,
        target_label: str,
        rows: list,
        deleted_at: datetime | None = None,
    ) -> DeletionBatch:
        deleted_at = deleted_at or datetime.now(timezone.utc)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.__tablename__] = counts.get(row.__tablename__, 0) + 1
        batch = DeletionBatch(
            entity_type=entity_type,
            entity_id=entity_id,
            target_label=target_label,
            deleted_by_user_id=self.admin_user.id,
            deleted_at=deleted_at,
            counts_json=counts,
        )
        self.db.add(batch)
        self.db.flush()
        for row in rows:
            row.deleted_at = deleted_at
            row.deleted_batch_id = batch.id
        self.db.commit()
        return batch

    def _entry_url(self, entry_id: str, suffix: str = "") -> str:
        return f"/api/v1/admin/trash/{quote(entry_id, safe='')}{suffix}"

    def test_deleted_student_appears_in_unified_and_filtered_trash_and_restores_from_either(self):
        tree = self._student_tree("ZZ-TEST-UNIFIED")
        student = tree["student"]
        response = self.client.delete(f"/api/v1/students/{student.id}", headers=self._headers())
        self.assertEqual(response.status_code, 200)

        unified = self.client.get("/api/v1/admin/trash", headers=self._headers())
        filtered = self.client.get("/api/v1/admin/trash?entity_type=student", headers=self._headers())
        self.assertEqual(unified.status_code, 200)
        self.assertEqual(filtered.status_code, 200)
        unified_ids = {entry["entity_id"]: entry for entry in unified.json()["entries"]}
        filtered_ids = {entry["entity_id"]: entry for entry in filtered.json()["entries"]}
        self.assertIn(str(student.id), unified_ids)
        self.assertIn(str(student.id), filtered_ids)

        restore = self.client.post(self._entry_url(filtered_ids[str(student.id)]["id"], "/restore"), headers=self._headers())
        self.assertEqual(restore.status_code, 200)
        self.db.expire_all()
        self.assertIsNone(self.db.get(Student, student.id).deleted_at)

    def test_restore_child_while_parent_deleted_returns_409_then_restores_after_parent(self):
        tree = self._student_tree("ZZ-TEST-RESTORE-ORDER")
        student = tree["student"]
        enrollment = tree["enrollment"]
        deleted_at = datetime.now(timezone.utc)
        student.deleted_at = deleted_at
        enrollment.deleted_at = deleted_at
        self.db.commit()

        child_entry = f"row:enrollments:{enrollment.id}"
        blocked = self.client.post(self._entry_url(child_entry, "/restore"), headers=self._headers())
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"]["code"], "restore_parent_deleted")

        parent_entry = f"row:students:{student.id}"
        restore_parent = self.client.post(self._entry_url(parent_entry, "/restore"), headers=self._headers())
        restore_child = self.client.post(self._entry_url(child_entry, "/restore"), headers=self._headers())
        self.assertEqual(restore_parent.status_code, 200)
        self.assertEqual(restore_child.status_code, 200)
        self.db.expire_all()
        self.assertIsNone(self.db.get(Student, student.id).deleted_at)
        self.assertIsNone(self.db.get(Enrollment, enrollment.id).deleted_at)

    def test_per_row_purge_student_full_tree_has_no_orphans_and_preserves_other_rows(self):
        tree = self._student_tree("ZZ-TEST-PURGE")
        other_tree = self._student_tree("ZZ-TEST-KEEP")
        student = tree["student"]
        student_id = student.id
        other_student_id = other_tree["student"].id
        other_enrollment_id = other_tree["enrollment"].id
        other_grade_id = other_tree["grade"].id
        student.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

        purge = self.client.delete(self._entry_url(f"row:students:{student_id}"), headers=self._headers())
        self.assertEqual(purge.status_code, 200)

        self.db.expire_all()
        self.assertIsNone(self.db.get(Student, student_id))
        self.assertEqual(self.db.scalar(select(func.count(StudentParent.id)).where(StudentParent.student_id == student_id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(Enrollment.id)).where(Enrollment.student_id == student_id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(Grade.id)).where(Grade.student_id == student_id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(CourseResult.id)).where(CourseResult.student_id == student_id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(ReportCard.id)).where(ReportCard.student_id == student_id)), 0)
        self.assertIsNotNone(self.db.get(Student, other_student_id))
        self.assertIsNotNone(self.db.get(Enrollment, other_enrollment_id))
        self.assertIsNotNone(self.db.get(Grade, other_grade_id))

    def test_batch_student_purge_flushes_every_deleted_batch_reference_before_batch(self):
        tree = self._student_tree("ZZ-TEST-BATCH-STUDENT")
        student_id = tree["student"].id
        batch = self._batch_rows(
            entity_type="student",
            entity_id=student_id,
            target_label="ZZ-TEST Batch Student",
            rows=list(tree.values()),
        )
        batch_id = batch.id

        response = self.client.delete(self._entry_url(f"batch:{batch_id}"), headers=self._headers())
        self.assertEqual(response.status_code, 200, response.text)

        self.db.expire_all()
        self.assertIsNone(self.db.get(DeletionBatch, batch_id))
        self.assertIsNone(self.db.get(Student, student_id))
        for model in RECOVERABLE_MODELS.values():
            remaining = self.db.scalar(
                select(func.count()).select_from(model).where(model.deleted_batch_id == batch_id)
            )
            self.assertEqual(remaining, 0, model.__tablename__)

    @patch("routes.parents.send_account_created_sms", return_value=[])
    @patch("routes.parents.send_account_created_email", return_value={"success": False})
    def test_batch_parent_purge_deletes_user_tokens_preserves_audit_and_reuses_email(self, _email, _sms):
        user = self._user(
            name="ZZ-TEST-Batch Parent",
            email="zz-test-batch-parent@example.test",
            role="parent",
        )
        parent = Parent(user=user, phone="+2290100000011")
        self.db.add(parent)
        self.db.flush()
        token = PasswordResetToken(
            user_id=user.id,
            token_hash="b" * 64,
            token_version=user.token_version,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=45),
        )
        audit = AuditLog(
            actor_user_id=user.id,
            action="ZZ-TEST-parent-action",
            entity_type="parent",
            entity_id=parent.id,
        )
        self.db.add_all([token, audit])
        self.db.commit()
        user_id = user.id
        parent_id = parent.id
        token_id = token.id
        audit_id = audit.id
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": self.password},
        )
        self.assertEqual(login.status_code, 200, login.text)
        pre_purge_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        batch = self._batch_rows(
            entity_type="parent",
            entity_id=parent_id,
            target_label="ZZ-TEST Batch Parent",
            rows=[parent],
        )

        response = self.client.delete(self._entry_url(f"batch:{batch.id}"), headers=self._headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(Parent, parent_id))
        self.assertIsNone(self.db.get(User, user_id))
        self.assertIsNone(self.db.get(PasswordResetToken, token_id))
        preserved_audit = self.db.get(AuditLog, audit_id)
        self.assertIsNotNone(preserved_audit)
        self.assertIsNone(preserved_audit.actor_user_id)
        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers=pre_purge_headers).status_code,
            401,
        )

        recreated = self.client.post(
            "/api/v1/parents",
            json={
                "name": "ZZ-TEST-Recreated Parent",
                "email": "zz-test-batch-parent@example.test",
                "phone": "+2290100000012",
            },
            headers=self._headers(),
        )
        self.assertEqual(recreated.status_code, 201, recreated.text)

    def test_batch_teacher_purge_deletes_linked_user(self):
        user = self._user(
            name="ZZ-TEST-Batch Teacher",
            email="zz-test-batch-teacher@example.test",
            role="teacher",
        )
        teacher = Teacher(user=user, employee_number="ZZ-TEST-BATCH-TCH")
        self.db.add(teacher)
        self.db.commit()
        user_id = user.id
        teacher_id = teacher.id
        batch = self._batch_rows(
            entity_type="teacher",
            entity_id=teacher_id,
            target_label="ZZ-TEST Batch Teacher",
            rows=[teacher],
        )

        response = self.client.delete(self._entry_url(f"batch:{batch.id}"), headers=self._headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(Teacher, teacher_id))
        self.assertIsNone(self.db.get(User, user_id))

    def test_role_changed_batch_owner_guard_preserves_account_and_history(self):
        user = self._user(
            name="ZZ-TEST-Former Admin Parent",
            email="zz-test-former-admin-parent@example.test",
            role="parent",
        )
        parent = Parent(user=user, phone="+2290100000013", deleted_at=datetime.now(timezone.utc))
        self.db.add(parent)
        self.db.flush()
        owned_batch = DeletionBatch(
            entity_type="student",
            entity_id=parent.id,
            target_label="ZZ-TEST Historical Batch",
            deleted_by_user_id=user.id,
            deleted_at=datetime.now(timezone.utc),
            counts_json={},
        )
        self.db.add(owned_batch)
        self.db.commit()
        user_id = user.id
        parent_id = parent.id
        owned_batch_id = owned_batch.id

        response = self.client.delete(
            self._entry_url(f"row:parents:{parent_id}"),
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "purge_user_owns_deletion_batches")
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Parent, parent_id))
        self.assertIsNotNone(self.db.get(User, user_id))
        self.assertIsNotNone(self.db.get(DeletionBatch, owned_batch_id))

    def test_per_row_purge_deletes_only_selected_entry(self):
        first = self._student_tree("ZZ-TEST-PURGE-ONE")["student"]
        second = self._student_tree("ZZ-TEST-PURGE-TWO")["student"]
        first_id = first.id
        second_id = second.id
        now = datetime.now(timezone.utc)
        first.deleted_at = now
        second.deleted_at = now
        self.db.commit()

        response = self.client.delete(self._entry_url(f"row:students:{first_id}"), headers=self._headers())
        self.assertEqual(response.status_code, 200)

        self.db.expire_all()
        self.assertIsNone(self.db.get(Student, first_id))
        self.assertIsNotNone(self.db.get(Student, second_id))
        self.assertIsNotNone(self.db.get(Student, second_id).deleted_at)

    def test_empty_trash_purges_everything_and_audits_counts(self):
        first = self._student_tree("ZZ-TEST-EMPTY-ONE")["student"]
        second = self._student_tree("ZZ-TEST-EMPTY-TWO")["student"]
        now = datetime.now(timezone.utc)
        first.deleted_at = now
        second.deleted_at = now
        self.db.commit()

        response = self.client.delete("/api/v1/admin/trash", headers=self._headers())
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["counts"]["students"], 2)

        audit = self.db.scalar(select(AuditLog).where(AuditLog.action == "trash_emptied"))
        self.assertIsNotNone(audit)
        self.assertGreaterEqual(audit.new_value["counts"]["students"], 2)

    def test_empty_trash_purges_mixed_batch_and_unbatched_role_accounts(self):
        teacher_user = self._user(
            name="ZZ-TEST-Mixed Teacher",
            email="zz-test-mixed-teacher@example.test",
            role="teacher",
        )
        teacher = Teacher(user=teacher_user, employee_number="ZZ-TEST-MIXED-TCH")
        parent_user = self._user(
            name="ZZ-TEST-Mixed Parent",
            email="zz-test-mixed-parent@example.test",
            role="parent",
        )
        parent = Parent(
            user=parent_user,
            phone="+2290100000021",
            deleted_at=datetime.now(timezone.utc),
        )
        self.db.add_all([teacher, parent])
        self.db.commit()
        teacher_user_id = teacher_user.id
        teacher_id = teacher.id
        parent_user_id = parent_user.id
        parent_id = parent.id
        batch = self._batch_rows(
            entity_type="teacher",
            entity_id=teacher_id,
            target_label="ZZ-TEST Mixed Teacher",
            rows=[teacher],
        )
        batch_id = batch.id

        response = self.client.delete("/api/v1/admin/trash", headers=self._headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(DeletionBatch, batch_id))
        self.assertIsNone(self.db.get(Teacher, teacher_id))
        self.assertIsNone(self.db.get(User, teacher_user_id))
        self.assertIsNone(self.db.get(Parent, parent_id))
        self.assertIsNone(self.db.get(User, parent_user_id))

    def test_auto_purge_uses_deleted_at_retention_boundary(self):
        old_student = self._student_tree("ZZ-TEST-OLD")["student"]
        kept_student = self._student_tree("ZZ-TEST-KEPT")["student"]
        old_student_id = old_student.id
        kept_student_id = kept_student.id
        old_student.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        kept_student.deleted_at = datetime.now(timezone.utc) - timedelta(days=29)
        self.db.commit()

        response = self.client.get("/api/v1/admin/trash", headers=self._headers())
        self.assertEqual(response.status_code, 200)

        self.db.expire_all()
        self.assertIsNone(self.db.get(Student, old_student_id))
        kept = self.db.get(Student, kept_student_id)
        self.assertIsNotNone(kept)
        self.assertIsNotNone(kept.deleted_at)
        entries = {entry["entity_id"] for entry in response.json()["entries"]}
        self.assertIn(str(kept_student_id), entries)

    def test_auto_purge_removes_expired_teacher_batch_and_user(self):
        user = self._user(
            name="ZZ-TEST-Expired Teacher",
            email="zz-test-expired-teacher@example.test",
            role="teacher",
        )
        teacher = Teacher(user=user, employee_number="ZZ-TEST-EXPIRED-TCH")
        self.db.add(teacher)
        self.db.commit()
        user_id = user.id
        teacher_id = teacher.id
        batch = self._batch_rows(
            entity_type="teacher",
            entity_id=teacher_id,
            target_label="ZZ-TEST Expired Teacher",
            rows=[teacher],
            deleted_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        batch_id = batch.id

        response = self.client.get("/api/v1/admin/trash", headers=self._headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(DeletionBatch, batch_id))
        self.assertIsNone(self.db.get(Teacher, teacher_id))
        self.assertIsNone(self.db.get(User, user_id))

    def test_purged_item_is_unrecoverable(self):
        student = self._student_tree("ZZ-TEST-UNRECOVERABLE")["student"]
        student.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        entry = f"row:students:{student.id}"

        purge = self.client.delete(self._entry_url(entry), headers=self._headers())
        restore = self.client.post(self._entry_url(entry, "/restore"), headers=self._headers())
        self.assertEqual(purge.status_code, 200)
        self.assertEqual(restore.status_code, 404)


if __name__ == "__main__":
    unittest.main()
