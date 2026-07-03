import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, User


class ChangePasswordTests(unittest.TestCase):
    password = "old-password-1"

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
            name="Change PW User",
            email="changepw@example.test",
            password_hash=hash_password(self.password),
            role="parent",
            must_change_password=True,
        )
        db.add(self.user)
        db.commit()
        db.refresh(self.user)
        db.close()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _login(self, password: str = "") -> str:
        pw = password or self.password
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "changepw@example.test", "password": pw},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _auth_headers(self, password: str = "") -> dict[str, str]:
        return {"Authorization": f"Bearer {self._login(password)}"}

    # --- login response includes must_change_password ---

    def test_login_response_includes_must_change_password_true(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "changepw@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["must_change_password"])

    def test_me_includes_must_change_password_true(self):
        response = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["must_change_password"])

    # --- successful change ---

    def test_valid_new_password_accepted_and_flag_cleared(self):
        response = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "brand-new-password-99"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

        # must_change_password is now False
        me_response = self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_headers("brand-new-password-99"),
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertFalse(me_response.json()["must_change_password"])

    def test_old_password_no_longer_works_after_change(self):
        self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "another-new-pw-42"},
            headers=self._auth_headers(),
        )
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "changepw@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 401)

    # --- validation ---

    def test_password_shorter_than_8_chars_rejected(self):
        response = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "short"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 422)

    def test_change_password_requires_auth(self):
        response = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "some-new-password"},
        )
        self.assertEqual(response.status_code, 401)

    def test_change_password_with_bad_token_returns_401(self):
        response = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "some-new-password"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(response.status_code, 401)
