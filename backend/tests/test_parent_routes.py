import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Parent, User


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


if __name__ == "__main__":
    unittest.main()
