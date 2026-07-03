import os
import unittest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)


class DangerZoneRouteTests(unittest.TestCase):
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
        self._seed_graph()

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

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _seed_graph(self) -> None:
        self.admin_user = self._user(name="Admin User", email="admin-danger@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher User", email="teacher-danger@example.test", role="teacher")
        self.parent_user = self._user(name="Parent User", email="parent-danger@example.test", role="parent")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="DZ-TCH")
        self.parent = Parent(user=self.parent_user, phone="555-0001")
        self.school_class = Class(
            name_fr="6eme DZ",
            name_en="Grade 6 DZ",
            school_level="college",
            stream=None,
            sort_order=1,
            school_year="2026-2027",
        )
        self.student = Student(
            first_name="Demo",
            last_name="Student",
            grade_level="6",
            school_level="college",
            student_number="DZ-STU",
            school_class=self.school_class,
        )
        self.db.add_all([self.teacher, self.parent, self.school_class, self.student])
        self.db.flush()
        self.link = StudentParent(student=self.student, parent=self.parent, relationship="mother")
        self.course = Course(
            name="Danger Math",
            code="DZ-MATH",
            teacher=self.teacher,
            grade_level="6",
            term="1er Trimestre",
            school_year="2026-2027",
            school_class=self.school_class,
        )
        self.db.add_all([self.link, self.course])
        self.db.flush()
        self.enrollment = Enrollment(student=self.student, course=self.course)
        self.grade_item = GradeItem(
            course=self.course,
            title="Quiz",
            category="Quiz",
            max_score=20,
            weight=1,
            term="1er Trimestre",
        )
        self.db.add_all([self.enrollment, self.grade_item])
        self.db.flush()
        self.grade = Grade(
            student=self.student,
            grade_item=self.grade_item,
            score=18,
            submitted_by_teacher=self.teacher,
        )
        self.result = CourseResult(
            student=self.student,
            course=self.course,
            term="1er Trimestre",
            average=18,
            letter_grade="A",
            scale="20",
        )
        self.report = ReportCard(
            student=self.student,
            term="1er Trimestre",
            school_year="2026-2027",
            overall_average=18,
            scale="20",
            status="approved",
        )
        self.db.add_all([self.grade, self.result, self.report])
        self.db.flush()
        self.report_course = ReportCardCourse(
            report_card=self.report,
            course=self.course,
            course_name=self.course.name,
            average=18,
            letter_grade="A",
        )
        self.db.add(self.report_course)
        self.db.commit()

    def test_non_admin_cannot_preview_or_delete(self):
        headers = self._headers(self.teacher_user.email)
        search = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=teacher&q=teacher",
            headers=headers,
        )
        preview = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=teacher&entity_id={self.teacher.id}",
            headers=headers,
        )
        delete = self.client.post(
            "/api/v1/admin/danger-zone/delete",
            json={"entity_type": "teacher", "entity_id": str(self.teacher.id), "confirmation": "MOVE TO TRASH"},
            headers=headers,
        )

        self.assertEqual(search.status_code, 403)
        self.assertEqual(preview.status_code, 403)
        self.assertEqual(delete.status_code, 403)

    def test_search_returns_human_labels_for_teacher_class_course_and_student(self):
        headers = self._headers(self.admin_user.email)

        teacher_response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=teacher&q=Teacher",
            headers=headers,
        )
        self.assertEqual(teacher_response.status_code, 200)
        self.assertEqual(
            teacher_response.json()[0],
            {
                "id": str(self.teacher.id),
                "label": "Teacher User",
                "subtitle": "teacher-danger@example.test",
                "entity_type": "teacher",
            },
        )

        class_response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=class&q=6eme",
            headers=headers,
        )
        self.assertEqual(class_response.status_code, 200)
        self.assertEqual(class_response.json()[0]["label"], "6eme DZ")
        self.assertEqual(class_response.json()[0]["subtitle"], "2026-2027 · Collège")

        course_response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=course&q=math",
            headers=headers,
        )
        self.assertEqual(course_response.status_code, 200)
        self.assertEqual(course_response.json()[0]["label"], "Danger Math")
        self.assertEqual(course_response.json()[0]["subtitle"], "6eme DZ · 2026-2027 · teacher-danger@example.test")

        student_response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=student&q=DZ-STU",
            headers=headers,
        )
        self.assertEqual(student_response.status_code, 200)
        self.assertEqual(student_response.json()[0]["label"], "Demo Student")
        self.assertEqual(student_response.json()[0]["subtitle"], "DZ-STU · 6eme DZ")

    def test_search_excludes_trashed_records(self):
        self.teacher.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

        response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=teacher&q=Teacher",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_preview_works_with_id_returned_from_search(self):
        headers = self._headers(self.admin_user.email)
        search_response = self.client.get(
            "/api/v1/admin/danger-zone/search?entity_type=course&q=math",
            headers=headers,
        )
        self.assertEqual(search_response.status_code, 200)
        selected_id = search_response.json()[0]["id"]

        preview_response = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=course&entity_id={selected_id}",
            headers=headers,
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response.json()["target_label"], "Danger Math (DZ-MATH)")
        self.assertEqual(preview_response.json()["counts"]["courses"], 1)

    def test_production_guard_blocks_without_flag(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("ENABLE_DANGER_ZONE", None)
            response = self.client.get(
                f"/api/v1/admin/danger-zone/preview?entity_type=teacher&entity_id={self.teacher.id}",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 403)

    def test_preview_counts_teacher_dependency_bundle(self):
        response = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=teacher&entity_id={self.teacher.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        counts = response.json()["counts"]
        self.assertEqual(counts["teachers"], 1)
        self.assertEqual(counts["courses"], 1)
        self.assertEqual(counts["enrollments"], 1)
        self.assertEqual(counts["grade_items"], 1)
        self.assertEqual(counts["grades"], 1)
        self.assertEqual(counts["course_results"], 1)
        self.assertEqual(counts["report_cards"], 1)
        self.assertEqual(counts["report_card_courses"], 1)

    def test_confirmation_is_required(self):
        response = self.client.post(
            "/api/v1/admin/danger-zone/delete",
            json={"entity_type": "teacher", "entity_id": str(self.teacher.id), "confirmation": "DELETE"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 400)

    def test_move_teacher_bundle_to_trash_and_restore(self):
        move_response = self.client.post(
            "/api/v1/admin/danger-zone/delete",
            json={"entity_type": "teacher", "entity_id": str(self.teacher.id), "confirmation": "MOVE TO TRASH"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(move_response.status_code, 200)
        batch_id = UUID(move_response.json()["batch_id"])

        self.db.expire_all()
        batch = self.db.get(DeletionBatch, batch_id)
        self.assertIsNotNone(batch)
        for row in (
            self.db.get(Teacher, self.teacher.id),
            self.db.get(Course, self.course.id),
            self.db.get(Enrollment, self.enrollment.id),
            self.db.get(GradeItem, self.grade_item.id),
            self.db.get(Grade, self.grade.id),
            self.db.get(CourseResult, self.result.id),
            self.db.get(ReportCard, self.report.id),
            self.db.get(ReportCardCourse, self.report_course.id),
        ):
            self.assertIsNotNone(row.deleted_at)
            self.assertEqual(row.deleted_batch_id, batch_id)

        hidden_courses = self.client.get("/api/v1/courses", headers=self._headers(self.admin_user.email))
        self.assertEqual(hidden_courses.status_code, 200)
        self.assertEqual(hidden_courses.json(), [])

        hidden_reports = self.client.get(
            f"/api/v1/reports/student/{self.student.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(hidden_reports.status_code, 200)
        self.assertEqual(hidden_reports.json(), [])

        audits = self.db.scalars(select(AuditLog).where(AuditLog.action == "danger_zone_moved_to_trash")).all()
        self.assertEqual(len(audits), 1)

        restore_response = self.client.post(
            f"/api/v1/admin/danger-zone/batches/{batch_id}/restore",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(restore_response.status_code, 200)

        self.db.expire_all()
        self.assertIsNone(self.db.get(Teacher, self.teacher.id).deleted_at)
        self.assertIsNone(self.db.get(Course, self.course.id).deleted_at)
        self.assertIsNone(self.db.get(ReportCard, self.report.id).deleted_at)
        restored_audits = self.db.scalars(select(AuditLog).where(AuditLog.action == "danger_zone_restored")).all()
        self.assertEqual(len(restored_audits), 1)

    def test_class_course_student_and_parent_previews_follow_scope_rules(self):
        headers = self._headers(self.admin_user.email)

        class_preview = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=class&entity_id={self.school_class.id}",
            headers=headers,
        )
        self.assertEqual(class_preview.status_code, 200)
        self.assertEqual(class_preview.json()["counts"]["classes"], 1)
        self.assertEqual(class_preview.json()["counts"]["courses"], 1)
        self.assertNotIn("students", class_preview.json()["counts"])

        student_preview = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=student&entity_id={self.student.id}",
            headers=headers,
        )
        self.assertEqual(student_preview.status_code, 200)
        self.assertEqual(student_preview.json()["counts"]["students"], 1)
        self.assertEqual(student_preview.json()["counts"]["student_parents"], 1)
        self.assertNotIn("parents", student_preview.json()["counts"])

        parent_preview = self.client.get(
            f"/api/v1/admin/danger-zone/preview?entity_type=parent&entity_id={self.parent.id}",
            headers=headers,
        )
        self.assertEqual(parent_preview.status_code, 200)
        self.assertEqual(parent_preview.json()["counts"]["parents"], 1)
        self.assertNotIn("students", parent_preview.json()["counts"])


if __name__ == "__main__":
    unittest.main()
