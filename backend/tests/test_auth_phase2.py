import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Parent, PasswordResetToken, Teacher, User
from services.password_reset_tokens import issue_reset_token, token_digest


class AuthPhase2Tests(unittest.TestCase):
    password = "phase-two-password-123"

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
        self.admin = User(
            name="ZZ-TEST-Admin",
            email="zz-phase2-admin@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        teacher_user = User(
            name="ZZ-TEST-Teacher",
            email="zz-phase2-teacher@example.test",
            password_hash=hash_password(self.password),
            role="teacher",
        )
        self.teacher = Teacher(
            user=teacher_user,
            phone="+22961000999",
            employee_number="ZZ-TEST-PHASE2-TCH",
        )
        db.add_all([self.admin, teacher_user, self.teacher])
        db.commit()
        self.admin_id = self.admin.id
        self.teacher_id = self.teacher.id
        self.teacher_user_id = teacher_user.id
        db.close()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def login(self, identifier: str, password: str | None = None) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": identifier, "password": password or self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_teacher_and_admin_shared_profile_settings(self):
        teacher_token = self.login("ZZ-TEST-PHASE2-TCH")
        teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
        profile = self.client.get("/api/v1/auth/profile", headers=teacher_headers)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["phone"], "+22961000999")
        updated = self.client.put(
            "/api/v1/auth/profile",
            json={"name": "ZZ-TEST-Teacher Updated", "phone": "+22997000000"},
            headers=teacher_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["phone"], "+22997000000")

        admin_token = self.login("zz-phase2-admin@example.test")
        admin_updated = self.client.put(
            "/api/v1/auth/profile",
            json={"name": "ZZ-TEST-Admin Updated", "phone": "+229IGNORED"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(admin_updated.status_code, 200)
        self.assertIsNone(admin_updated.json()["phone"])

    def test_missing_teacher_profile_blocks_login_and_preexisting_jwt_without_version_bump(self):
        token = self.login("zz-phase2-teacher@example.test")
        headers = {"Authorization": f"Bearer {token}"}
        db = self.SessionLocal()
        user = db.get(User, self.teacher_user_id)
        original_token_version = user.token_version
        teacher = db.get(Teacher, self.teacher_id)
        db.delete(teacher)
        db.commit()
        db.refresh(user)
        self.assertEqual(user.token_version, original_token_version)
        db.close()

        relogin = self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "zz-phase2-teacher@example.test", "password": self.password},
        )
        self.assertEqual(relogin.status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 401)

    def test_parent_shared_profile_and_password_change(self):
        db = self.SessionLocal()
        parent_user = User(
            name="ZZ-TEST-Parent",
            email="zz-phase2-parent@example.test",
            password_hash=hash_password(self.password),
            role="parent",
        )
        parent = Parent(user=parent_user, phone="+22961000888")
        db.add_all([parent_user, parent])
        db.commit()
        db.close()

        old_token = self.login("zz-phase2-parent@example.test")
        headers = {"Authorization": f"Bearer {old_token}"}
        profile = self.client.get("/api/v1/auth/profile", headers=headers)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["phone"], "+22961000888")

        updated = self.client.put(
            "/api/v1/auth/profile",
            json={"name": "ZZ-TEST-Parent Updated", "phone": "+22997000888"},
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "ZZ-TEST-Parent Updated")
        self.assertEqual(updated.json()["phone"], "+22997000888")

        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": self.password, "new_password": "parent-new-password-456"},
            headers=headers,
        )
        self.assertEqual(changed.status_code, 200)
        fresh_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=fresh_headers).status_code, 200)

    @patch("services.account_security.send_temporary_password_reset_email", return_value={"success": True})
    def test_admin_reset_invalidates_target_and_audits_without_password(self, _send):
        old_token = self.login("ZZ-TEST-PHASE2-TCH")
        admin_token = self.login("zz-phase2-admin@example.test")
        response = self.client.post(
            f"/api/v1/teachers/{self.teacher_id}/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        temp_password = response.json()["temp_password"]
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            ).status_code,
            401,
        )
        db = self.SessionLocal()
        user = db.get(User, self.teacher_user_id)
        self.assertTrue(user.must_change_password)
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "admin_password_reset"))
        self.assertIsNotNone(audit)
        self.assertNotIn(temp_password, str(audit.new_value))
        db.close()

    @patch("routes.auth.send_password_reset_email", return_value={"success": True})
    def test_email_reset_single_use_admin_recovery_and_no_repeat_email(self, send_email):
        first = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"identifier": "zz-phase2-admin@example.test"},
        )
        second = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"identifier": "zz-phase2-admin@example.test"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        send_email.assert_called_once()
        raw_token = send_email.call_args.args[2]

        completed = self.client.post(
            "/api/v1/auth/reset-password/email",
            json={"token": raw_token, "new_password": "phase-two-new-password"},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/reset-password/email",
                json={"token": raw_token, "new_password": "another-new-password"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"identifier": "zz-phase2-admin@example.test", "password": "phase-two-new-password"},
            ).status_code,
            200,
        )
        db = self.SessionLocal()
        actions = set(db.scalars(select(AuditLog.action)).all())
        self.assertIn("email_password_reset_requested", actions)
        self.assertIn("email_password_reset_completed", actions)
        db.close()

    @patch("routes.auth.send_password_reset_email", return_value={"success": True})
    def test_unknown_and_trashed_email_are_generic_without_token_or_email(self, send_email):
        unknown = self.client.post(
            "/api/v1/auth/forgot-password", json={"identifier": "unknown@example.test"}
        )
        db = self.SessionLocal()
        db.get(Teacher, self.teacher_id).deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
        trashed = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"identifier": "zz-phase2-teacher@example.test"},
        )
        self.assertEqual(unknown.json(), trashed.json())
        send_email.assert_not_called()
        db = self.SessionLocal()
        self.assertEqual(len(db.scalars(select(PasswordResetToken)).all()), 0)
        db.close()

    def test_expired_used_cleanup_and_new_issue_replaces_previous(self):
        db = self.SessionLocal()
        user = db.get(User, self.admin_id)
        first_raw = issue_reset_token(db, user)
        db.flush()
        second_raw = issue_reset_token(db, user)
        db.commit()
        self.assertIsNone(db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(first_raw))))
        active = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(second_raw)))
        active.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        used = PasswordResetToken(
            user_id=user.id,
            token_hash="a" * 64,
            token_version=user.token_version,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            used_at=datetime.now(timezone.utc),
        )
        db.add(used)
        db.commit()
        db.close()
        response = self.client.post(
            "/api/v1/auth/reset-password/email",
            json={"token": second_raw, "new_password": "cannot-use-expired"},
        )
        self.assertEqual(response.status_code, 400)
        db = self.SessionLocal()
        self.assertEqual(len(db.scalars(select(PasswordResetToken)).all()), 0)
        db.close()

    @patch("routes.auth.send_password_reset_email", return_value={"success": True})
    def test_email_link_invalidated_by_intervening_password_change(self, send_email):
        self.client.post(
            "/api/v1/auth/forgot-password",
            json={"identifier": "zz-phase2-teacher@example.test"},
        )
        raw_token = send_email.call_args.args[2]
        db = self.SessionLocal()
        db.get(User, self.teacher_user_id).token_version += 1
        db.commit()
        db.close()
        response = self.client.post(
            "/api/v1/auth/reset-password/email",
            json={"token": raw_token, "new_password": "cannot-use-version"},
        )
        self.assertEqual(response.status_code, 400)

    def test_login_and_password_events_are_audited(self):
        self.client.post(
            "/api/v1/auth/login",
            json={"identifier": "zz-phase2-admin@example.test", "password": "wrong-password"},
        )
        token = self.login("zz-phase2-admin@example.test")
        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": self.password, "new_password": "audit-new-password"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(changed.status_code, 200)
        db = self.SessionLocal()
        actions = set(db.scalars(select(AuditLog.action)).all())
        self.assertTrue({"auth_login_failed", "auth_login_succeeded", "password_changed"}.issubset(actions))
        failed = db.scalar(select(AuditLog).where(AuditLog.action == "auth_login_failed"))
        self.assertIsNone(failed.actor_user_id)
        self.assertEqual(failed.new_value, {"identifier_type": "email"})
        db.close()

    @patch("routes.auth.check_otp", return_value=True)
    def test_forced_change_and_otp_reset_events_are_audited(self, _otp):
        db = self.SessionLocal()
        user = db.get(User, self.teacher_user_id)
        user.must_change_password = True
        db.commit()
        db.close()
        token = self.login("ZZ-TEST-PHASE2-TCH")
        forced = self.client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "forced-phase-two-password"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(forced.status_code, 200)
        otp = self.client.post(
            "/api/v1/auth/reset-password",
            json={
                "identifier": "ZZ-TEST-PHASE2-TCH",
                "otp": "123456",
                "new_password": "otp-phase-two-password",
            },
        )
        self.assertEqual(otp.status_code, 200)
        db = self.SessionLocal()
        actions = set(db.scalars(select(AuditLog.action)).all())
        self.assertIn("forced_password_change_completed", actions)
        self.assertIn("otp_password_reset_completed", actions)
        db.close()
