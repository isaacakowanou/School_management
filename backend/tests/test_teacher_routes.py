import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Teacher, User


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
        self.db.add(self.existing_teacher)
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
            "password": "new-teacher-password",
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

        user = self.db.scalar(select(User).where(User.email == "new-teacher@example.test"))
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "New Teacher")
        self.assertEqual(user.role, "teacher")

        teacher = self.db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        self.assertIsNotNone(teacher)
        self.assertEqual(str(teacher.id), data["id"])

    def test_created_teacher_can_log_in_with_raw_password(self):
        response = self.client.post(
            "/api/v1/teachers",
            json=self._teacher_payload(email="login-teacher@example.test", employee_number="TCH-LOGIN"),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 201)

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "login-teacher@example.test", "password": "new-teacher-password"},
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access_token", login_response.json())

    def test_create_teacher_trims_required_fields(self):
        response = self.client.post(
            "/api/v1/teachers",
            json={
                "name": "  Trimmed Teacher  ",
                "email": "  trimmed-teacher@example.test  ",
                "password": "  trimmed-password  ",
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
                "password": "new-teacher-password",
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
                "employee_number": "TCH-AUDIT",
            },
        )


if __name__ == "__main__":
    unittest.main()
