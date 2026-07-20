import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Parent, Teacher, User


class ParentSelfServiceTests(unittest.TestCase):
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

    def _seed(self):
        self.parent_user = User(
            name="Pat Parent",
            email="pat@example.test",
            password_hash=hash_password(self.password),
            role="parent",
        )
        self.admin_user = User(
            name="Admin User",
            email="admin@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        self.teacher_user = User(
            name="Taylor Teacher",
            email="teacher@example.test",
            password_hash=hash_password(self.password),
            role="teacher",
        )
        self.db.add_all([self.parent_user, self.admin_user, self.teacher_user])
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-PARENT-SELF-TCH")
        self.db.add_all([self.parent, self.teacher])
        self.db.commit()

    def _login(self, email: str) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _headers(self, email: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._login(email)}"}

    # --- GET /me (sanity) ---

    def test_parent_can_get_own_profile(self):
        response = self.client.get("/api/v1/parents/me", headers=self._headers(self.parent_user.email))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Pat Parent")
        self.assertEqual(data["phone"], "555-0100")

    # --- PUT /me ---

    def test_parent_can_update_own_name(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "Patricia Parent"},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Patricia Parent")
        self.assertEqual(data["phone"], "555-0100")

        self.db.expire_all()
        self.assertEqual(self.parent_user.name, "Patricia Parent")

    def test_parent_can_update_own_phone(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"phone": "555-9999"},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phone"], "555-9999")

    def test_parent_can_clear_own_phone(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"phone": None},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["phone"])

        self.db.expire_all()
        self.assertIsNone(self.parent.phone)

    def test_phone_only_whitespace_is_treated_as_cleared(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"phone": "   "},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["phone"])

    def test_name_is_trimmed(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "  Pat  "},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Pat")

    def test_empty_name_rejected(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": " "},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_omitting_phone_does_not_clear_it(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "New Name"},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phone"], "555-0100")

    def test_email_field_is_ignored(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "Pat Parent", "email": "hacker@evil.test"},
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "pat@example.test")

    def test_admin_cannot_use_self_update_route(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "Admin Tries"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_use_self_update_route(self):
        response = self.client.put(
            "/api/v1/parents/me",
            json={"name": "Teacher Tries"},
            headers=self._headers(self.teacher_user.email),
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_request_rejected(self):
        response = self.client.put("/api/v1/parents/me", json={"name": "No Auth"})
        self.assertEqual(response.status_code, 401)
