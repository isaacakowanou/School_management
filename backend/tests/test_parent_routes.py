import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Course, Grade, GradeItem, Parent, Student, StudentParent, Teacher, User


class CurrentParentRouteTests(unittest.TestCase):
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
        self._create_test_users()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_user(self, *, name: str, email: str, role: str) -> User:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(self.password),
            role=role,
        )
        self.db.add(user)
        return user

    def _create_test_users(self) -> None:
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-current.test@example.test",
            role="parent",
        )
        self.parent_without_profile_user = self._create_user(
            name="No Profile Parent",
            email="parent-no-profile.test@example.test",
            role="parent",
        )
        self.admin_user = self._create_user(
            name="Admin User",
            email="admin-current-parent.test@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-current-parent.test@example.test",
            role="teacher",
        )
        self.other_parent_user = self._create_user(
            name="Other Parent",
            email="other-parent-current.test@example.test",
            role="parent",
        )
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.other_parent = Parent(user=self.other_parent_user, phone="555-0101")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-PARENT-GRADES")
        self.db.add_all([self.parent, self.other_parent, self.teacher])
        self.db.commit()

    def _login(self, email: str) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _auth_headers(self, email: str) -> dict[str, str]:
        token = self._login(email)
        return {"Authorization": f"Bearer {token}"}

    def _parent_payload(self, email: str = "new-parent@example.test") -> dict[str, str]:
        return {
            "name": "New Parent",
            "email": email,
            "phone": "555-0199",
        }

    def _seed_parent_grade_data(self):
        school_class = Class(
            name_fr="6ème",
            school_level="college",
            sort_order=1,
            school_year="2026-2027",
        )
        student = Student(first_name="Ada", last_name="Lovelace", student_number="PG001", school_class=school_class)
        unlinked_student = Student(first_name="Grace", last_name="Hopper", student_number="PG002", school_class=school_class)
        self.db.add_all([school_class, student, unlinked_student])
        self.db.flush()
        link = StudentParent(student=student, parent=self.parent, relationship="Guardian")
        self.db.add(link)
        course = Course(
            name="Mathématique",
            code="PARENT-GRADE-MATH",
            teacher=self.teacher,
            term="2ème Trimestre",
            school_year="2026-2027",
            school_class=school_class,
        )
        self.db.add(course)
        self.db.flush()
        first_item = GradeItem(
            course=course,
            title="Interro 1",
            category=None,
            item_type="INTERRO",
            max_score=20,
            term="1er Trimestre",
        )
        second_item = GradeItem(
            course=course,
            title="Devoir 1",
            category=None,
            item_type="DEVOIR",
            max_score=20,
            term="2ème Trimestre",
        )
        empty_item = GradeItem(
            course=course,
            title="Composition",
            category=None,
            item_type="COMPOSITION",
            max_score=20,
            term="2ème Trimestre",
        )
        self.db.add_all([first_item, second_item, empty_item])
        self.db.flush()
        now = datetime.now(timezone.utc)
        first_grade = Grade(
            student=student,
            grade_item=first_item,
            score=15,
            submitted_by_teacher=self.teacher,
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=9),
        )
        second_grade = Grade(
            student=student,
            grade_item=second_item,
            score=17,
            submitted_by_teacher=self.teacher,
            created_at=now - timedelta(days=1),
            updated_at=now,
        )
        unlinked_grade = Grade(
            student=unlinked_student,
            grade_item=second_item,
            score=18,
            submitted_by_teacher=self.teacher,
        )
        self.db.add_all([first_grade, second_grade, unlinked_grade])
        self.db.commit()
        return {
            "student": student,
            "unlinked_student": unlinked_student,
            "link": link,
            "first_item": first_item,
            "second_item": second_item,
        }

    def test_parent_token_can_get_current_parent_profile(self):
        response = self.client.get(
            "/api/v1/parents/me",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.parent.id))
        self.assertEqual(data["user_id"], str(self.parent_user.id))
        self.assertEqual(data["name"], self.parent_user.name)
        self.assertEqual(data["email"], self.parent_user.email)
        self.assertEqual(data["phone"], self.parent.phone)
        self.assertNotIn("password_hash", data)

    def test_admin_token_cannot_get_current_parent_profile(self):
        response = self.client.get(
            "/api/v1/parents/me",
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_teacher_token_cannot_get_current_parent_profile(self):
        response = self.client.get(
            "/api/v1/parents/me",
            headers=self._auth_headers(self.teacher_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_parent_without_profile_cannot_authenticate(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.parent_without_profile_user.email,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid credentials")

    def test_admin_can_create_parent(self):
        response = self.client.post(
            "/api/v1/parents",
            json=self._parent_payload(),
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "New Parent")
        self.assertEqual(data["email"], "new-parent@example.test")
        self.assertEqual(data["phone"], "555-0199")
        self.assertIn("temp_password", data)
        self.assertGreater(len(data["temp_password"]), 0)

        user = self.db.scalar(select(User).where(User.email == "new-parent@example.test"))
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "New Parent")
        self.assertEqual(user.role, "parent")
        self.assertTrue(user.must_change_password)

        parent = self.db.scalar(select(Parent).where(Parent.user_id == user.id))
        self.assertIsNotNone(parent)
        self.assertEqual(str(parent.id), data["id"])

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "new-parent@example.test", "password": data["temp_password"]},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["must_change_password"])

    def test_create_parent_trims_fields_and_allows_empty_phone(self):
        response = self.client.post(
            "/api/v1/parents",
            json={
                "name": "  Trimmed Parent  ",
                "email": "  trimmed-parent@example.test  ",
                "phone": "   ",
            },
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "Trimmed Parent")
        self.assertEqual(data["email"], "trimmed-parent@example.test")
        self.assertIsNone(data["phone"])

    def test_non_admin_cannot_create_parent(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/parents",
                    json=self._parent_payload(f"new-parent-{user.role}@example.test"),
                    headers=self._auth_headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_parent_email_is_rejected(self):
        response = self.client.post(
            "/api/v1/parents",
            json=self._parent_payload(self.parent_user.email),
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Email already exists")

    def test_empty_parent_required_fields_are_rejected(self):
        response = self.client.post(
            "/api/v1/parents",
            json={
                "name": " ",
                "email": "empty-parent@example.test",
                "phone": None,
            },
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_create_parent_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/parents",
            json=self._parent_payload("audit-parent@example.test"),
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        parent_id = UUID(response.json()["id"])
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "parent_created",
                AuditLog.entity_type == "parent",
                AuditLog.entity_id == parent_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "user_id": str(response.json()["user_id"]),
                "name": "New Parent",
                "email": "audit-parent@example.test",
                "phone": "555-0199",
            },
        )

    def test_admin_delete_parent_blocked_when_linked_to_active_student(self):
        student = Student(first_name="Active", last_name="Student", student_number="PDEL-ACTIVE")
        self.db.add(student)
        self.db.flush()
        self.db.add(StudentParent(student=student, parent=self.parent, relationship="Guardian"))
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/parents/{self.parent.id}",
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["active_student_count"], 1)
        self.assertIsNotNone(self.db.get(Parent, self.parent.id))

    def test_admin_can_delete_unlinked_parent_and_audits(self):
        parent_id = self.parent.id

        response = self.client.delete(
            f"/api/v1/parents/{parent_id}",
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Parent, parent_id).deleted_at)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "parent_deleted",
                AuditLog.entity_type == "parent",
                AuditLog.entity_id == parent_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)

    def test_non_admin_cannot_delete_parent(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.delete(
                    f"/api/v1/parents/{self.parent.id}",
                    headers=self._auth_headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_admin_can_update_parent(self):
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={
                "name": "  Edited Parent  ",
                "email": "  edited-parent@example.test  ",
                "phone": "   ",
            },
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Edited Parent")
        self.assertEqual(data["email"], "edited-parent@example.test")
        self.assertIsNone(data["phone"])

    def test_non_admin_cannot_update_parent(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.put(
                    f"/api/v1/parents/{self.parent.id}",
                    json={"name": "Blocked"},
                    headers=self._auth_headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_update_parent_duplicate_email_is_rejected(self):
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={"email": self.admin_user.email},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Email already exists")

    def test_update_parent_empty_required_field_is_rejected(self):
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={"name": " "},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_update_parent_writes_audit_log(self):
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={"name": "Audit Parent"},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "parent_updated",
                AuditLog.entity_type == "parent",
                AuditLog.entity_id == self.parent.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(audit_log.old_value["name"], "Pat Parent")
        self.assertEqual(audit_log.new_value["name"], "Audit Parent")

    # --- Email-optional ---

    def test_create_parent_without_email_succeeds(self):
        response = self.client.post(
            "/api/v1/parents",
            json={"name": "No Email Parent", "phone": "555-0001"},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "No Email Parent")
        self.assertIsNone(data["email"])
        self.assertEqual(data["phone"], "555-0001")
        self.assertIn("temp_password", data)

    def test_parent_without_email_logs_in_with_phone(self):
        create = self.client.post(
            "/api/v1/parents",
            json={"name": "No Email Parent", "phone": "555-7777"},
            headers=self._auth_headers(self.admin_user.email),
        )
        self.assertEqual(create.status_code, 201)
        temp_password = create.json()["temp_password"]

        login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "555-7777", "password": temp_password},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["role"], "parent")

    def test_update_parent_can_clear_email_via_null(self):
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={"email": None},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["email"])
        self.db.expire_all()
        self.assertIsNone(self.db.get(User, self.parent.user_id).email)

    def test_update_parent_omitting_email_leaves_it_unchanged(self):
        original_email = self.parent_user.email
        response = self.client.put(
            f"/api/v1/parents/{self.parent.id}",
            json={"name": "Renamed Only"},
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.get(User, self.parent.user_id).email, original_email)

    # --- Parent grade view ---

    def test_parent_can_list_own_student_grades_for_shared_current_term(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["course_name"], "Mathématique")
        self.assertEqual(data[0]["item_title"], "Interro 1")
        self.assertEqual(data[0]["item_type"], "INTERRO")
        self.assertEqual(data[0]["score"], 15)
        self.assertEqual(data[0]["max_score"], 20)
        self.assertEqual(data[0]["term"], "1er Trimestre")
        self.assertEqual(data[0]["school_year"], "2026-2027")
        self.assertNotIn("average", data[0])
        self.assertNotIn("moy", data[0])
        self.assertNotIn("course_result", data[0])

    def test_parent_can_request_past_term_after_school_advances(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades?term=1er Trimestre",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["item_title"], "Interro 1")
        self.assertEqual(data[0]["term"], "1er Trimestre")

    def test_parent_student_grades_reject_unlinked_student(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['unlinked_student'].id}/grades",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_parent_student_grades_reject_inactive_link(self):
        seeded = self._seed_parent_grade_data()
        seeded["link"].deleted_at = datetime.now(timezone.utc)
        self.db.commit()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_parent_student_grades_empty_when_no_scores_for_term(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades?term=3ème Trimestre",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_parent_student_grades_reject_non_canonical_term(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades?term=Midterm",
            headers=self._auth_headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 422)

    def test_non_parent_cannot_list_parent_student_grades(self):
        seeded = self._seed_parent_grade_data()

        response = self.client.get(
            f"/api/v1/parents/me/students/{seeded['student'].id}/grades",
            headers=self._auth_headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
