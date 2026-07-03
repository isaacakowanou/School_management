import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, User


class AuthRouteTests(unittest.TestCase):
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

        db = self.SessionLocal()
        self.user = User(
            name="Auth Test Admin",
            email="auth-test@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        db.add(self.user)
        db.commit()
        db.close()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _login(self) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "auth-test@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    # --- Login ---

    def test_valid_credentials_return_200_with_token(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "auth-test@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "admin")
        self.assertEqual(data["token_type"], "bearer")

    def test_wrong_password_returns_401(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "auth-test@example.test", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)

    def test_unknown_email_returns_401(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 401)

    # --- /me ---

    def test_me_returns_current_user(self):
        token = self._login()
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "auth-test@example.test")
        self.assertEqual(data["role"], "admin")
        self.assertNotIn("password_hash", data)

    def test_me_without_token_returns_401(self):
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    # --- Logout ---

    def test_logout_with_valid_token_returns_200(self):
        token = self._login()
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_logout_without_token_returns_401(self):
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 401)

    def test_logout_with_bad_token_returns_401(self):
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        self.assertEqual(response.status_code, 401)
