import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Parent, User


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
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.db.add(self.parent)
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
            "password": "new-parent-password",
            "phone": "555-0199",
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

    def test_parent_without_profile_gets_404(self):
        response = self.client.get(
            "/api/v1/parents/me",
            headers=self._auth_headers(self.parent_without_profile_user.email),
        )

        self.assertEqual(response.status_code, 404)

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

        user = self.db.scalar(select(User).where(User.email == "new-parent@example.test"))
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "New Parent")
        self.assertEqual(user.role, "parent")

        parent = self.db.scalar(select(Parent).where(Parent.user_id == user.id))
        self.assertIsNotNone(parent)
        self.assertEqual(str(parent.id), data["id"])

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "new-parent@example.test", "password": "new-parent-password"},
        )
        self.assertEqual(login_response.status_code, 200)

    def test_create_parent_trims_fields_and_allows_empty_phone(self):
        response = self.client.post(
            "/api/v1/parents",
            json={
                "name": "  Trimmed Parent  ",
                "email": "  trimmed-parent@example.test  ",
                "password": "  trimmed-password  ",
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
                "password": "new-parent-password",
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


if __name__ == "__main__":
    unittest.main()
