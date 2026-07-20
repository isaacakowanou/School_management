import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Course, Grade, GradeItem, Parent, Student, Teacher, User


class TeacherRouteTests(unittest.TestCase):
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
        self._seed_users()

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

    def _seed_users(self) -> None:
        self.admin_user = self._create_user(
            name="Admin User",
            email="admin-teachers@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-teachers@example.test",
            role="teacher",
        )
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-teachers@example.test",
            role="parent",
        )
        self.db.flush()
        self.existing_teacher = Teacher(user=self.teacher_user, employee_number="TCH-EXISTING")
        self.parent = Parent(user=self.parent_user, phone="+2290100000087")
        self.db.add_all([self.existing_teacher, self.parent])
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _teacher_payload(
        self,
        *,
        email: str = "new-teacher@example.test",
        employee_number: str = "TCH-NEW-001",
    ) -> dict[str, str]:
        return {
            "name": "New Teacher",
            "email": email,
            "employee_number": employee_number,
        }

    def test_admin_can_create_teacher(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "New Teacher")
        self.assertEqual(data["email"], "new-teacher@example.test")
        self.assertEqual(data["employee_number"], "TCH-NEW-001")
        self.assertIn("temp_password", data)
        self.assertGreater(len(data["temp_password"]), 0)

        user = self.db.scalar(select(User).where(User.email == "new-teacher@example.test"))
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "New Teacher")
        self.assertEqual(user.role, "teacher")
        self.assertTrue(user.must_change_password)

        teacher = self.db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        self.assertIsNotNone(teacher)
        self.assertEqual(str(teacher.id), data["id"])

    def test_created_teacher_can_log_in_with_temp_password(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(email="login-teacher@example.test", employee_number="TCH-LOGIN"),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 201)
        temp_password = response.json()["temp_password"]

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "login-teacher@example.test", "password": temp_password},
        )

        self.assertEqual(login_response.status_code, 200)
        login_data = login_response.json()
        self.assertIn("access_token", login_data)
        self.assertTrue(login_data["must_change_password"])

    def test_create_teacher_trims_required_fields(self):
        response = self.client.post(
            "/api/v1/teachers",
            json={
                "name": "  Trimmed Teacher  ",
                "email": "  trimmed-teacher@example.test  ",
                "employee_number": "  TCH-TRIM  ",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "Trimmed Teacher")
        self.assertEqual(data["email"], "trimmed-teacher@example.test")
        self.assertEqual(data["employee_number"], "TCH-TRIM")

    def test_non_admin_cannot_create_teacher(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/teachers",
                    json=self._teacher_payload(
                        email=f"new-teacher-{user.role}@example.test",
                        employee_number=f"TCH-{user.role.upper()}",
                    ),
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_teacher_email_is_rejected(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(email=self.teacher_user.email),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Email already exists")

    def test_duplicate_employee_number_is_rejected(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(employee_number=self.existing_teacher.employee_number),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Employee number already exists")

    def test_empty_teacher_required_fields_are_rejected(self):
        response = self.client.post(
            "/api/v1/teachers",
            json={
                "name": " ",
                "email": "empty-teacher@example.test",
                "employee_number": "TCH-EMPTY",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_create_teacher_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(email="audit-teacher@example.test", employee_number="TCH-AUDIT"),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        teacher_id = UUID(response.json()["id"])
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "teacher_created",
                AuditLog.entity_type == "teacher",
                AuditLog.entity_id == teacher_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "user_id": str(response.json()["user_id"]),
                "name": "New Teacher",
                "email": "audit-teacher@example.test",
                "phone": None,
                "employee_number": "TCH-AUDIT",
            },
        )

    def test_admin_delete_teacher_blocked_when_courses_exist(self):
        course = Course(
            name="Teacher Course",
            code="TDEL-COURSE",
            teacher=self.existing_teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.db.add(course)
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["course_count"], 1)
        self.assertIsNotNone(self.db.get(Teacher, self.existing_teacher.id))

    def test_admin_delete_teacher_blocked_when_submitted_grades_exist(self):
        other_user = self._create_user(
            name="Other Teacher",
            email="teacher-grade-owner@example.test",
            role="teacher",
        )
        self.db.flush()
        course_teacher = Teacher(user=other_user, employee_number="TCH-GRADE-OWNER")
        self.db.add(course_teacher)
        self.db.flush()
        course = Course(
            name="Past Course",
            code="TDEL-GRADE",
            teacher=course_teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        student = Student(first_name="Ada", last_name="Lovelace", student_number="TDEL-STU")
        self.db.add_all([course, student])
        self.db.flush()
        grade_item = GradeItem(course=course, title="Exam", category="Exam", max_score=20, weight=1, term="1er Trimestre")
        self.db.add(grade_item)
        self.db.flush()
        grade = Grade(student=student, grade_item=grade_item, score=18, submitted_by_teacher=self.existing_teacher)
        self.db.add(grade)
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["submitted_grade_count"], 1)

    def test_admin_can_delete_teacher_with_no_courses_or_grades_and_audits(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(email="delete-teacher@example.test", employee_number="TCH-DELETE"),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 201)
        teacher_id = UUID(response.json()["id"])

        delete_response = self.client.delete(
            f"/api/v1/teachers/{teacher_id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(delete_response.status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Teacher, teacher_id).deleted_at)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "teacher_deleted",
                AuditLog.entity_type == "teacher",
                AuditLog.entity_id == teacher_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)

    def test_non_admin_cannot_delete_teacher(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.delete(
                    f"/api/v1/teachers/{self.existing_teacher.id}",
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_admin_can_update_teacher(self):
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={
                "name": "  Edited Teacher  ",
                "email": "  edited-teacher@example.test  ",
                "employee_number": "  TCH-EDITED  ",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Edited Teacher")
        self.assertEqual(data["email"], "edited-teacher@example.test")
        self.assertEqual(data["employee_number"], "TCH-EDITED")

    def test_non_admin_cannot_update_teacher(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.put(
                    f"/api/v1/teachers/{self.existing_teacher.id}",
                    json={"name": "Blocked"},
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_update_teacher_duplicate_email_is_rejected(self):
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"email": self.parent_user.email},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Email already exists")

    def test_update_teacher_duplicate_employee_number_is_rejected(self):
        other_user = self._create_user(
            name="Other Teacher",
            email="other-teacher@example.test",
            role="teacher",
        )
        other_teacher = Teacher(user=other_user, employee_number="TCH-OTHER")
        self.db.add(other_teacher)
        self.db.commit()

        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"employee_number": "TCH-OTHER"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Employee number already exists")

    def test_update_teacher_empty_required_field_is_rejected(self):
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"employee_number": " "},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "employee_number cannot be empty")

    def test_update_teacher_writes_audit_log(self):
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"name": "Audit Teacher"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "teacher_updated",
                AuditLog.entity_type == "teacher",
                AuditLog.entity_id == self.existing_teacher.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(audit_log.old_value["name"], "Taylor Teacher")
        self.assertEqual(audit_log.new_value["name"], "Audit Teacher")

    # --- Email-optional ---

    def test_create_teacher_without_email_succeeds(self):
        response = self.client.post(
            "/api/v1/teachers",
            json={"name": "No Email Teacher", "employee_number": "TCH-NOEMAIL"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "No Email Teacher")
        self.assertIsNone(data["email"])
        self.assertEqual(data["employee_number"], "TCH-NOEMAIL")
        self.assertIn("temp_password", data)

    def test_teacher_without_email_logs_in_with_employee_number(self):
        create = self.client.post(
            "/api/v1/teachers",
            json={"name": "No Email Teacher", "employee_number": "TCH-EMPNUM"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(create.status_code, 201)
        temp_password = create.json()["temp_password"]

        login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "TCH-EMPNUM", "password": temp_password},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["role"], "teacher")

    def test_update_teacher_can_clear_email_via_null(self):
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"email": None},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["email"])
        self.db.expire_all()
        self.assertIsNone(self.db.get(User, self.existing_teacher.user_id).email)

    def test_update_teacher_omitting_email_leaves_it_unchanged(self):
        original_email = self.teacher_user.email
        response = self.client.put(
            f"/api/v1/teachers/{self.existing_teacher.id}",
            json={"name": "Renamed Only"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.get(User, self.existing_teacher.user_id).email, original_email)


if __name__ == "__main__":
    unittest.main()
