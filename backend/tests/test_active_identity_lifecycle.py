"""Active-only account identity and Corbeille restore regressions."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, DeletionBatch, Parent, PasswordResetToken, Teacher, User


class ActiveIdentityLifecycleTests(unittest.TestCase):
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
        self.admin = self._user("ZZ-TEST Admin", "zz-active-admin@example.test", "admin")
        self.parent_user = self._user("ZZ-TEST Parent", "zz-active-parent@example.test", "parent")
        self.teacher_user = self._user("ZZ-TEST Teacher", "zz-active-teacher@example.test", "teacher")
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="ZZ-TEST-PARENT-PHONE")
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-EMPLOYEE")
        self.db.add_all([self.parent, self.teacher])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, name: str, email: str, role: str) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _login(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self) -> dict[str, str]:
        return self._login(self.admin.email)

    def _trash_restore_url(self, entry_id: str) -> str:
        return f"/api/v1/admin/trash/{quote(entry_id, safe='')}/restore"

    @patch("routes.parents.send_account_created_sms", return_value=[])
    @patch("routes.parents.send_account_created_email", return_value={"success": False})
    def test_deleted_parent_email_is_reusable_and_old_credentials_stay_blocked(self, _email, _sms):
        old_headers = self._login(self.parent_user.email)
        deleted = self.client.delete(f"/api/v1/parents/{self.parent.id}", headers=self._admin())
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(User, self.parent_user.id).deleted_at)

        recreated = self.client.post(
            "/api/v1/parents",
            json={"name": "ZZ-TEST Replacement Parent", "email": self.parent_user.email},
            headers=self._admin(),
        )
        self.assertEqual(recreated.status_code, 201, recreated.text)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=old_headers).status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"email": self.parent_user.email, "password": self.password},
            ).status_code,
            401,
        )

    @patch("routes.teachers.send_account_created_sms", return_value=[])
    @patch("routes.teachers.send_account_created_email", return_value={"success": False})
    def test_deleted_teacher_email_and_employee_number_are_reusable(self, _email, _sms):
        deleted = self.client.delete(f"/api/v1/teachers/{self.teacher.id}", headers=self._admin())
        self.assertEqual(deleted.status_code, 200, deleted.text)

        recreated = self.client.post(
            "/api/v1/teachers",
            json={
                "name": "ZZ-TEST Replacement Teacher",
                "email": self.teacher_user.email,
                "employee_number": self.teacher.employee_number,
            },
            headers=self._admin(),
        )
        self.assertEqual(recreated.status_code, 201, recreated.text)

    @patch("routes.parents.send_account_created_sms", return_value=[])
    @patch("routes.parents.send_account_created_email", return_value={"success": False})
    @patch("routes.teachers.send_account_created_sms", return_value=[])
    @patch("routes.teachers.send_account_created_email", return_value={"success": False})
    def test_active_duplicate_email_is_blocked_across_roles(self, _teacher_email, _teacher_sms, _parent_email, _parent_sms):
        parent = self.client.post(
            "/api/v1/parents",
            json={"name": "ZZ-TEST Duplicate Parent", "email": self.admin.email},
            headers=self._admin(),
        )
        teacher = self.client.post(
            "/api/v1/teachers",
            json={
                "name": "ZZ-TEST Duplicate Teacher",
                "email": self.parent_user.email,
                "employee_number": "ZZ-TEST-OTHER-EMPLOYEE",
            },
            headers=self._admin(),
        )
        self.assertEqual(parent.status_code, 409)
        self.assertEqual(teacher.status_code, 409)

    @patch("routes.auth.send_password_reset_email", return_value={"success": True})
    def test_password_recovery_ignores_deleted_account(self, send_email):
        deleted = self.client.delete(f"/api/v1/parents/{self.parent.id}", headers=self._admin())
        self.assertEqual(deleted.status_code, 200, deleted.text)
        response = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"identifier": self.parent_user.email},
        )
        self.assertEqual(response.status_code, 200)
        send_email.assert_not_called()
        self.assertEqual(self.db.scalars(select(PasswordResetToken)).all(), [])

    @patch("routes.parents.send_account_created_sms", return_value=[])
    @patch("routes.parents.send_account_created_email", return_value={"success": False})
    def test_per_row_restore_conflict_then_succeeds_after_replacement_is_deleted(self, _email, _sms):
        original_token_version = self.parent_user.token_version
        deleted = self.client.delete(f"/api/v1/parents/{self.parent.id}", headers=self._admin())
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.db.expire_all()
        deleted_token_version = self.db.get(User, self.parent_user.id).token_version
        self.assertGreater(deleted_token_version, original_token_version)

        replacement = self.client.post(
            "/api/v1/parents",
            json={"name": "ZZ-TEST Replacement", "email": self.parent_user.email},
            headers=self._admin(),
        )
        self.assertEqual(replacement.status_code, 201, replacement.text)
        conflict = self.client.post(
            self._trash_restore_url(f"row:parents:{self.parent.id}"),
            headers=self._admin(),
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "restore_email_conflict")
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Parent, self.parent.id).deleted_at)
        self.assertIsNotNone(self.db.get(User, self.parent_user.id).deleted_at)

        replacement_id = replacement.json()["id"]
        removed = self.client.delete(f"/api/v1/parents/{replacement_id}", headers=self._admin())
        self.assertEqual(removed.status_code, 200, removed.text)
        restored = self.client.post(
            self._trash_restore_url(f"row:parents:{self.parent.id}"),
            headers=self._admin(),
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(Parent, self.parent.id).deleted_at)
        self.assertIsNone(self.db.get(User, self.parent_user.id).deleted_at)
        self.assertEqual(self.db.get(User, self.parent_user.id).token_version, deleted_token_version)

    @patch("routes.parents.send_account_created_sms", return_value=[])
    @patch("routes.parents.send_account_created_email", return_value={"success": False})
    def test_batch_and_danger_zone_restore_share_email_conflict_check(self, _email, _sms):
        deleted_at = datetime.now(timezone.utc)
        batch = DeletionBatch(
            entity_type="parent",
            entity_id=self.parent.id,
            target_label="ZZ-TEST Parent",
            deleted_by_user_id=self.admin.id,
            deleted_at=deleted_at,
            counts_json={"parents": 1},
        )
        self.db.add(batch)
        self.db.flush()
        self.parent.deleted_at = deleted_at
        self.parent.deleted_batch_id = batch.id
        self.parent_user.deleted_at = deleted_at
        self.db.commit()
        replacement = self.client.post(
            "/api/v1/parents",
            json={"name": "ZZ-TEST Batch Replacement", "email": self.parent_user.email},
            headers=self._admin(),
        )
        self.assertEqual(replacement.status_code, 201, replacement.text)

        unified = self.client.post(
            self._trash_restore_url(f"batch:{batch.id}"), headers=self._admin()
        )
        danger = self.client.post(
            f"/api/v1/admin/danger-zone/batches/{batch.id}/restore", headers=self._admin()
        )
        self.assertEqual(unified.status_code, 409, unified.text)
        self.assertEqual(danger.status_code, 409, danger.text)
        self.assertEqual(unified.json()["detail"]["code"], "restore_email_conflict")
        self.assertEqual(danger.json()["detail"]["code"], "restore_email_conflict")
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Parent, self.parent.id).deleted_at)
        self.assertIsNone(self.db.get(DeletionBatch, batch.id).restored_at)

    @patch("routes.teachers.send_account_created_sms", return_value=[])
    @patch("routes.teachers.send_account_created_email", return_value={"success": False})
    def test_teacher_restore_reports_active_employee_number_conflict(self, _email, _sms):
        deleted = self.client.delete(f"/api/v1/teachers/{self.teacher.id}", headers=self._admin())
        self.assertEqual(deleted.status_code, 200, deleted.text)
        replacement = self.client.post(
            "/api/v1/teachers",
            json={
                "name": "ZZ-TEST Employee Conflict",
                "email": "zz-active-teacher-replacement@example.test",
                "employee_number": self.teacher.employee_number,
            },
            headers=self._admin(),
        )
        self.assertEqual(replacement.status_code, 201, replacement.text)

        conflict = self.client.post(
            self._trash_restore_url(f"row:teachers:{self.teacher.id}"),
            headers=self._admin(),
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(
            conflict.json()["detail"]["code"],
            "restore_employee_number_conflict",
        )


if __name__ == "__main__":
    unittest.main()
