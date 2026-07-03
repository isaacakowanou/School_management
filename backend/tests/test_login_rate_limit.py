import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, User


class LoginRateLimitTests(unittest.TestCase):
    password = "valid-password-123"

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

        # Re-enable the limiter (conftest disables it globally) and start clean.
        app.state.limiter.enabled = True
        app.state.limiter._storage.reset()

        db = self.SessionLocal()
        user = User(
            name="Rate Limit Test User",
            email="ratelimit@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.close()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        # Leave the limiter disabled so the conftest post-yield step restores correctly.
        app.state.limiter.enabled = False

    def test_five_failed_logins_succeed_sixth_returns_429(self):
        for _ in range(5):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit@example.test", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.test", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 429)

    def test_successful_logins_also_count_toward_limit(self):
        for _ in range(5):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit@example.test", "password": self.password},
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.test", "password": self.password},
        )
        self.assertEqual(response.status_code, 429)

    def test_429_response_body_describes_rate_limit(self):
        for _ in range(5):
            self.client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit@example.test", "password": "wrong"},
            )
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.test", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 429)
        # slowapi returns a JSON detail with the rate limit info
        body = response.json()
        self.assertIn("error", body)
