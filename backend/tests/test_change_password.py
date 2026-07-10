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
        old_token = self._login()
        response = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "brand-new-password-99"},
            headers={"Authorization": f"Bearer {old_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        fresh_token = response.json()["access_token"]

        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh_token}"}).status_code,
            200,
        )

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

    def test_forced_user_is_blocked_except_me_change_and_logout(self):
        token = self._login()
        headers = {"Authorization": f"Bearer {token}"}
        blocked = self.client.get("/api/v1/parents/me", headers=headers)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["detail"]["code"], "password_change_required")
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=headers).status_code, 200)

        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "forced-change-99"},
            headers=headers,
        )
        self.assertEqual(changed.status_code, 200)
        fresh_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/v1/parents/me", headers=fresh_headers).status_code, 404)

    def test_voluntary_change_requires_correct_current_password(self):
        db = self.SessionLocal()
        user = db.get(User, self.user.id)
        user.must_change_password = False
        db.commit()
        db.close()
        token = self._login()
        headers = {"Authorization": f"Bearer {token}"}

        missing = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "voluntary-new-99"},
            headers=headers,
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["detail"]["code"], "current_password_required")

        wrong = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong-password", "new_password": "voluntary-new-99"},
            headers=headers,
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["detail"]["code"], "current_password_incorrect")

        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": self.password, "new_password": "voluntary-new-99"},
            headers=headers,
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
            ).status_code,
            200,
        )
