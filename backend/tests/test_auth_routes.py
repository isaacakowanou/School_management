import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Parent, Teacher, User


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
        self.user_id = self.user.id
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
        self.assertEqual(response.headers["x-error-code"], "invalid_credentials")

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

    def test_admin_without_role_profile_remains_authenticated(self):
        token = self._login()
        response = self.client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)

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

    # --- Alternative login credentials ---

    def test_login_with_employee_number_succeeds(self):
        db = self.SessionLocal()
        user = User(
            name="No Email Teacher",
            email=None,
            password_hash=hash_password(self.password),
            role="teacher",
        )
        teacher = Teacher(user=user, employee_number="TCH-2026-AUTH")
        db.add_all([user, teacher])
        db.commit()
        db.close()

        response = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "TCH-2026-AUTH", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["role"], "teacher")
        self.assertIn("access_token", data)

    def test_login_with_phone_succeeds(self):
        db = self.SessionLocal()
        user = User(
            name="No Email Parent",
            email=None,
            password_hash=hash_password(self.password),
            role="parent",
        )
        parent = Parent(user=user, phone="555-AUTH-TEST")
        db.add_all([user, parent])
        db.commit()
        db.close()

        response = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "555-AUTH-TEST", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["role"], "parent")
        self.assertIn("access_token", data)

    def test_login_email_key_still_accepted(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "auth-test@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)

    def test_wrong_employee_number_returns_401(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "TCH-9999-NOTEXIST", "password": self.password},
        )
        self.assertEqual(response.status_code, 401)

    def test_deleted_teacher_cannot_login_with_employee_number(self):
        db = self.SessionLocal()
        user = User(
            name="Deleted Teacher",
            email=None,
            password_hash=hash_password(self.password),
            role="teacher",
        )
        teacher = Teacher(
            user=user,
            employee_number="TCH-DELETED",
            deleted_at=datetime.now(timezone.utc),
        )
        db.add_all([user, teacher])
        db.commit()
        db.close()

        response = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "TCH-DELETED", "password": self.password},
        )
        self.assertEqual(response.status_code, 401)

    def test_trashed_teacher_email_and_employee_login_and_existing_token_are_blocked_until_restore(self):
        db = self.SessionLocal()
        user = User(
            name="ZZ-TEST-Trashed Teacher",
            email="zz-trashed-teacher@example.test",
            password_hash=hash_password(self.password),
            role="teacher",
        )
        teacher = Teacher(user=user, employee_number="ZZ-TEST-TRASH-TCH")
        db.add_all([user, teacher])
        db.commit()
        teacher_id = teacher.id
        db.close()

        active_login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "ZZ-TEST-TRASH-TCH", "password": self.password},
        )
        old_token = active_login.json()["access_token"]
        db = self.SessionLocal()
        db.get(Teacher, teacher_id).deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.close()

        for identifier in ("zz-trashed-teacher@example.test", "ZZ-TEST-TRASH-TCH"):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"identifier": identifier, "password": self.password},
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "Invalid credentials")
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            ).status_code,
            401,
        )

        db = self.SessionLocal()
        db.get(Teacher, teacher_id).deleted_at = None
        db.commit()
        db.close()
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"identifier": "ZZ-TEST-TRASH-TCH", "password": self.password},
            ).status_code,
            200,
        )

    def test_trashed_parent_email_and_phone_login_and_existing_token_are_blocked_until_restore(self):
        db = self.SessionLocal()
        user = User(
            name="ZZ-TEST-Trashed Parent",
            email="zz-trashed-parent@example.test",
            password_hash=hash_password(self.password),
            role="parent",
        )
        parent = Parent(user=user, phone="ZZ-TEST-PHONE")
        db.add_all([user, parent])
        db.commit()
        parent_id = parent.id
        db.close()

        active_login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "ZZ-TEST-PHONE", "password": self.password},
        )
        old_token = active_login.json()["access_token"]
        db = self.SessionLocal()
        db.get(Parent, parent_id).deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.close()

        for identifier in ("zz-trashed-parent@example.test", "ZZ-TEST-PHONE"):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"identifier": identifier, "password": self.password},
            )
            self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            ).status_code,
            401,
        )

        db = self.SessionLocal()
        db.get(Parent, parent_id).deleted_at = None
        db.commit()
        db.close()
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"identifier": "ZZ-TEST-PHONE", "password": self.password},
            ).status_code,
            200,
        )

    # --- Forgot password ---

    def _make_parent_with_phone(self, phone: str) -> Parent:
        db = self.SessionLocal()
        user = User(
            name="OTP Parent",
            email=None,
            password_hash=hash_password(self.password),
            role="parent",
        )
        parent = Parent(user=user, phone=phone)
        db.add_all([user, parent])
        db.commit()
        db.close()
        return parent

    def _make_teacher_with_phone(self, employee_number: str, phone: str) -> Teacher:
        db = self.SessionLocal()
        user = User(
            name="OTP Teacher",
            email=None,
            password_hash=hash_password(self.password),
            role="teacher",
        )
        teacher = Teacher(user=user, employee_number=employee_number, phone=phone)
        db.add_all([user, teacher])
        db.commit()
        db.close()
        return teacher

    def test_forgot_password_returns_200_for_existing_parent_phone(self):
        self._make_parent_with_phone("+22961000001")
        with patch("routes.auth.send_otp", return_value={"sent": True}) as mock_send:
            response = self.client.post(
                "/api/v1/auth/forgot-password",
                json={"identifier": "+22961000001"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("receive a code", response.json()["message"])
        mock_send.assert_called_once()

    def test_forgot_password_returns_200_for_existing_teacher_employee_number(self):
        self._make_teacher_with_phone("TCH-OTP-001", "+22961000002")
        with patch("routes.auth.send_otp", return_value={"sent": True}) as mock_send:
            response = self.client.post(
                "/api/v1/auth/forgot-password",
                json={"identifier": "TCH-OTP-001"},
            )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()

    def test_forgot_password_returns_200_for_unknown_identifier_no_enumeration(self):
        with patch("routes.auth.send_otp") as mock_send:
            response = self.client.post(
                "/api/v1/auth/forgot-password",
                json={"identifier": "completely-unknown"},
            )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_not_called()

    def test_forgot_password_otp_send_failure_still_returns_200(self):
        self._make_parent_with_phone("+22961000003")
        with patch("routes.auth.send_otp", side_effect=RuntimeError("Twilio down")):
            response = self.client.post(
                "/api/v1/auth/forgot-password",
                json={"identifier": "+22961000003"},
            )
        self.assertEqual(response.status_code, 200)

    # --- Reset password ---

    def test_reset_password_with_valid_otp_succeeds_for_parent(self):
        self._make_parent_with_phone("+22961000004")
        old_login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "+22961000004", "password": self.password},
        )
        old_token = old_login.json()["access_token"]
        with patch("routes.auth.send_otp"):
            self.client.post("/api/v1/auth/forgot-password", json={"identifier": "+22961000004"})

        with patch("routes.auth.check_otp", return_value=True):
            response = self.client.post(
                "/api/v1/auth/reset-password",
                json={"identifier": "+22961000004", "otp": "123456", "new_password": "newpass99"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

        # Verify the new password works for login.
        login = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "+22961000004", "password": "newpass99"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertFalse(login.json()["must_change_password"])
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            ).status_code,
            401,
        )

    def test_reset_password_with_valid_otp_succeeds_for_teacher(self):
        self._make_teacher_with_phone("TCH-OTP-002", "+22961000005")
        with patch("routes.auth.check_otp", return_value=True):
            response = self.client.post(
                "/api/v1/auth/reset-password",
                json={"identifier": "TCH-OTP-002", "otp": "123456", "new_password": "newpass99"},
            )
        self.assertEqual(response.status_code, 200)

    def test_reset_password_with_wrong_otp_returns_400(self):
        self._make_parent_with_phone("+22961000006")
        with patch("routes.auth.check_otp", return_value=False):
            response = self.client.post(
                "/api/v1/auth/reset-password",
                json={"identifier": "+22961000006", "otp": "000000", "new_password": "newpass99"},
            )
        self.assertEqual(response.status_code, 400)

    def test_reset_password_with_unknown_identifier_returns_400(self):
        with patch("routes.auth.check_otp", return_value=True):
            response = self.client.post(
                "/api/v1/auth/reset-password",
                json={"identifier": "nobody-here", "otp": "123456", "new_password": "newpass99"},
            )
        self.assertEqual(response.status_code, 400)

    def test_reset_password_too_short_returns_422(self):
        self._make_parent_with_phone("+22961000007")
        with patch("routes.auth.check_otp", return_value=True):
            response = self.client.post(
                "/api/v1/auth/reset-password",
                json={"identifier": "+22961000007", "otp": "123456", "new_password": "short"},
            )
        self.assertEqual(response.status_code, 422)

    def test_admin_password_update_invalidates_old_token_and_rejects_short_password(self):
        old_token = self._login()
        headers = {"Authorization": f"Bearer {old_token}"}
        short = self.client.put(
            f"/api/v1/users/{self.user_id}",
            json={"password": "short"},
            headers=headers,
        )
        self.assertEqual(short.status_code, 422)

        changed = self.client.put(
            f"/api/v1/users/{self.user_id}",
            json={"password": "admin-new-password-99"},
            headers=headers,
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers=headers).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"email": "auth-test@example.test", "password": "admin-new-password-99"},
            ).status_code,
            200,
        )
