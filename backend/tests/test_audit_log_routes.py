import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Parent, Teacher, User


class AuditLogRouteTests(unittest.TestCase):
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
        self._seed()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, *, name: str, email: str, role: str) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _seed(self) -> None:
        self.admin_user = self._user(name="Admin User", email="admin-audit@example.test", role="admin")
        self.teacher_user = self._user(
            name="Taylor Teacher",
            email="teacher-audit@example.test",
            role="teacher",
        )
        self.parent_user = self._user(name="Pat Parent", email="parent-audit@example.test", role="parent")
        self.db.flush()
        self.db.add_all(
            [
                Teacher(user=self.teacher_user, employee_number="ZZ-TEST-AUDIT-TCH"),
                Parent(user=self.parent_user, phone="+2290100000081"),
            ]
        )
        self.db.flush()

        self.entity_id = uuid.uuid4()
        self.audit_log = AuditLog(
            actor_user_id=self.teacher_user.id,
            action="grade_updated",
            entity_type="grade",
            entity_id=self.entity_id,
            old_value={"score": 88},
            new_value={"score": 92},
        )
        self.db.add(self.audit_log)
        self.db.commit()
        self.db.refresh(self.audit_log)

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_admin_audit_log_list_includes_actor_display_fields(self):
        response = self.client.get("/api/v1/audit-logs", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        audit_log = data[0]
        self.assertEqual(audit_log["id"], str(self.audit_log.id))
        self.assertEqual(audit_log["actor_user_id"], str(self.teacher_user.id))
        self.assertEqual(audit_log["actor_name"], "Taylor Teacher")
        self.assertEqual(audit_log["actor_email"], "teacher-audit@example.test")
        self.assertEqual(audit_log["old_value"], {"score": 88})
        self.assertEqual(audit_log["new_value"], {"score": 92})

    def test_actor_user_id_filter_still_works(self):
        response = self.client.get(
            f"/api/v1/audit-logs?actor_user_id={self.teacher_user.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

        response = self.client.get(
            f"/api/v1/audit-logs?actor_user_id={self.admin_user.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_non_admin_cannot_list_audit_logs(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.get("/api/v1/audit-logs", headers=self._headers(user.email))
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
