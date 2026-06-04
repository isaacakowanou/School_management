import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Parent, Student, StudentParent, User


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
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.db.add(self.parent)
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

    def _create_student(self, student_number: str = "LINK-STU-001") -> Student:
        student = Student(
            first_name="Link",
            last_name="Student",
            student_number=student_number,
            grade_level="12",
        )
        self.db.add(student)
        self.db.commit()
        self.db.refresh(student)
        return student

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

    def test_admin_can_link_parent_to_student(self):
        student = self._create_student()

        response = self.client.post(
            f"/api/v1/students/{student.id}/parents",
            json={"parent_id": str(self.parent.id), "relationship": "  Guardian  "},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], str(self.parent.id))
        self.assertEqual(data["user_id"], str(self.parent_user.id))
        self.assertEqual(data["name"], self.parent_user.name)
        self.assertEqual(data["email"], self.parent_user.email)
        self.assertEqual(data["relationship"], "Guardian")

        link = self.db.scalar(
            select(StudentParent).where(
                StudentParent.student_id == student.id,
                StudentParent.parent_id == self.parent.id,
            )
        )
        self.assertIsNotNone(link)
        self.assertEqual(link.relationship, "Guardian")

    def test_non_admin_cannot_link_parent_to_student(self):
        student = self._create_student("LINK-STU-NONADMIN")

        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    f"/api/v1/students/{student.id}/parents",
                    json={"parent_id": str(self.parent.id), "relationship": "Guardian"},
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_parent_student_link_is_rejected(self):
        student = self._create_student("LINK-STU-DUP")
        self.db.add(StudentParent(student=student, parent=self.parent, relationship="Guardian"))
        self.db.commit()

        response = self.client.post(
            f"/api/v1/students/{student.id}/parents",
            json={"parent_id": str(self.parent.id), "relationship": "Guardian"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Parent is already linked to student")

    def test_missing_student_or_parent_link_is_handled_cleanly(self):
        student = self._create_student("LINK-STU-MISSING")

        missing_student_response = self.client.post(
            f"/api/v1/students/{uuid4()}/parents",
            json={"parent_id": str(self.parent.id), "relationship": "Guardian"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(missing_student_response.status_code, 404)
        self.assertEqual(missing_student_response.json()["detail"], "Student not found")

        missing_parent_response = self.client.post(
            f"/api/v1/students/{student.id}/parents",
            json={"parent_id": str(uuid4()), "relationship": "Guardian"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(missing_parent_response.status_code, 404)
        self.assertEqual(missing_parent_response.json()["detail"], "Parent not found")

    def test_link_parent_to_student_writes_audit_log(self):
        student = self._create_student("LINK-STU-AUDIT")

        response = self.client.post(
            f"/api/v1/students/{student.id}/parents",
            json={"parent_id": str(self.parent.id), "relationship": "Mother"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        link = self.db.scalar(
            select(StudentParent).where(
                StudentParent.student_id == student.id,
                StudentParent.parent_id == self.parent.id,
            )
        )
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "parent_linked_to_student",
                AuditLog.entity_type == "student_parent",
                AuditLog.entity_id == link.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "student_id": str(student.id),
                "parent_id": str(self.parent.id),
                "relationship": "Mother",
            },
        )


if __name__ == "__main__":
    unittest.main()
