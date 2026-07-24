import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, TrimesterLock, User


class AcademicContextRouteTests(unittest.TestCase):
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
        self.admin = User(
            name="ZZ-TEST Context Admin",
            email="zz-test-context-admin@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        self.db.add(self.admin)
        self.db.add_all(
            [
                Class(name_fr="CM2", school_level="primaire", sort_order=6, school_year="2025-2026"),
                Class(name_fr="6ème", school_level="college", sort_order=7, school_year="2026-2027"),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _headers(self) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_current_context_uses_latest_class_year_and_first_unlocked_term(self):
        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["current_school_year"], "2026-2027")
        self.assertEqual(data["current_term"], "1er Trimestre")
        self.assertEqual(data["available_school_years"], ["2026-2027", "2025-2026"])

    def test_current_term_skips_locked_terms(self):
        self.db.add(
            TrimesterLock(
                school_year="2026-2027",
                term="1er Trimestre",
                is_locked=True,
                updated_by_admin_id=self.admin.id,
            )
        )
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["current_term"], "2ème Trimestre")

    def test_current_term_is_third_when_all_terms_locked(self):
        self.db.add_all(
            [
                TrimesterLock(
                    school_year="2026-2027",
                    term=term,
                    is_locked=True,
                    updated_by_admin_id=self.admin.id,
                )
                for term in ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
            ]
        )
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["current_term"], "3ème Trimestre")
