import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Student, User


class StudentRouteTests(unittest.TestCase):
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
            email="admin-students@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-students@example.test",
            role="teacher",
        )
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-students@example.test",
            role="parent",
        )
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _student_payload(self, student_number: str = "NEW-STU-001") -> dict[str, str]:
        return {
            "first_name": "New",
            "last_name": "Student",
            "student_number": student_number,
            "grade_level": "12",
        }

    def test_admin_can_create_student(self):
        response = self.client.post(
            "/api/v1/students",
            json=self._student_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["first_name"], "New")
        self.assertEqual(data["last_name"], "Student")
        self.assertEqual(data["student_number"], "NEW-STU-001")
        self.assertEqual(data["grade_level"], "12")

        student = self.db.scalar(select(Student).where(Student.student_number == "NEW-STU-001"))
        self.assertIsNotNone(student)

    def test_create_student_trims_required_fields(self):
        response = self.client.post(
            "/api/v1/students",
            json={
                "first_name": "  Trimmed  ",
                "last_name": "  Student  ",
                "student_number": "  NEW-STU-TRIM  ",
                "grade_level": "  11  ",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["first_name"], "Trimmed")
        self.assertEqual(data["last_name"], "Student")
        self.assertEqual(data["student_number"], "NEW-STU-TRIM")
        self.assertEqual(data["grade_level"], "11")

    def test_non_admin_cannot_create_student(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/students",
                    json=self._student_payload(f"NEW-STU-{user.role}"),
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_student_number_is_rejected(self):
        existing_student = Student(
            first_name="Existing",
            last_name="Student",
            student_number="DUP-STU-001",
            grade_level="12",
        )
        self.db.add(existing_student)
        self.db.commit()

        response = self.client.post(
            "/api/v1/students",
            json=self._student_payload("DUP-STU-001"),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Student number already exists")

    def test_empty_required_fields_are_rejected(self):
        response = self.client.post(
            "/api/v1/students",
            json={
                "first_name": " ",
                "last_name": "Student",
                "student_number": "EMPTY-STU-001",
                "grade_level": "12",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "first_name cannot be empty")

    def test_create_student_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/students",
            json=self._student_payload("AUDIT-STU-001"),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        student_id = UUID(response.json()["id"])
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "student_created",
                AuditLog.entity_type == "student",
                AuditLog.entity_id == student_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "first_name": "New",
                "last_name": "Student",
                "grade_level": "12",
                "student_number": "AUDIT-STU-001",
            },
        )


if __name__ == "__main__":
    unittest.main()
