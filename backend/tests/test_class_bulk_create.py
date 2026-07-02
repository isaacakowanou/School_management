import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from constants import CLASSES_BY_LEVEL_GROUP, GGFK_CLASSES
from database import get_db
from main import app
from models import AuditLog, Base, Class, Teacher, User

SCHOOL_YEAR = "2027-2028"


class GGFKClassListTests(unittest.TestCase):
    """Invariants of the canonical taxonomy list (A1.10)."""

    def test_has_exactly_18_classes(self):
        self.assertEqual(len(GGFK_CLASSES), 18)

    def test_names_are_unique(self):
        names = [entry["name_fr"] for entry in GGFK_CLASSES]
        self.assertEqual(len(names), len(set(names)))

    def test_level_group_mapping_derives_from_it(self):
        expected = {}
        for entry in GGFK_CLASSES:
            expected.setdefault(entry["level_group"], []).append(entry["name_fr"])
        self.assertEqual(expected, CLASSES_BY_LEVEL_GROUP)

    def test_streamed_classes_carry_full_name_and_stream(self):
        streamed = {e["name_fr"]: e["stream"] for e in GGFK_CLASSES if e["stream"] is not None}
        self.assertEqual(
            streamed,
            {"1ère C": "C", "1ère D": "D", "Terminale C": "C", "Terminale D": "D"},
        )

    def test_english_names_match_bulletin_headers(self):
        by_name = {e["name_fr"]: e["name_en"] for e in GGFK_CLASSES}
        self.assertEqual(by_name["6ème"], "JSS1")
        self.assertEqual(by_name["3ème"], "JSS4")
        self.assertEqual(by_name["2nde"], "SS1")
        self.assertEqual(by_name["1ère C"], "SS2")
        self.assertEqual(by_name["Terminale D"], "SS3")
        # Nursery and primary bulletins print the French name only.
        for entry in GGFK_CLASSES:
            if entry["school_level"] in ("maternelle", "primaire"):
                self.assertIsNone(entry["name_en"], entry["name_fr"])


class BulkCreateClassesTests(unittest.TestCase):
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

    def _user(self, *, name, email, role) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _seed(self):
        self.admin_user = self._user(name="Admin", email="admin-bulk@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-bulk@example.test", role="teacher")
        self.db.flush()
        self.db.add(Teacher(user=self.teacher_user, employee_number="T-BULK-1"))
        self.db.commit()

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _bulk_create(self, school_year=SCHOOL_YEAR, headers=None):
        return self.client.post(
            "/api/v1/classes/bulk-create",
            json={"school_year": school_year},
            headers=headers or self._headers(self.admin_user.email),
        )

    def test_creates_all_18_on_empty_year(self):
        r = self._bulk_create()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["created"]), 18)
        self.assertEqual(body["skipped"], [])

        rows = self.db.scalars(select(Class).where(Class.school_year == SCHOOL_YEAR)).all()
        self.assertEqual(len(rows), 18)
        by_name = {row.name_fr: row for row in rows}
        self.assertEqual(by_name["3ème"].name_en, "JSS4")
        self.assertEqual(by_name["3ème"].school_level, "college")
        self.assertEqual(by_name["1ère C"].stream, "C")
        self.assertEqual(by_name["1ère C"].name_en, "SS2")
        self.assertIsNone(by_name["CI"].name_en)
        self.assertEqual(by_name["CI"].school_level, "primaire")
        self.assertEqual(by_name["Pré-maternelle"].school_level, "maternelle")
        self.assertEqual(by_name["Terminale D"].sort_order, 9)

    def test_rerun_skips_all_18(self):
        self._bulk_create()
        r = self._bulk_create()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["created"], [])
        self.assertEqual(len(body["skipped"]), 18)
        count = len(self.db.scalars(select(Class).where(Class.school_year == SCHOOL_YEAR)).all())
        self.assertEqual(count, 18)

    def test_normalized_match_skips_hand_typed_variant(self):
        # A manually created "6eme" (no accent) counts as 6ème and is skipped.
        self.db.add(Class(name_fr="6eme", school_level="college", sort_order=1, school_year=SCHOOL_YEAR))
        self.db.commit()

        r = self._bulk_create()
        body = r.json()
        self.assertEqual(len(body["created"]), 17)
        self.assertEqual(body["skipped"], ["6ème"])
        self.assertNotIn("6ème", body["created"])

        rows = self.db.scalars(select(Class).where(Class.school_year == SCHOOL_YEAR)).all()
        self.assertEqual(len(rows), 18)  # 17 new + the hand-typed one
        names = {row.name_fr for row in rows}
        self.assertIn("6eme", names)
        self.assertNotIn("6ème", names)

    def test_other_years_do_not_cause_skips(self):
        self.db.add(Class(name_fr="6ème", school_level="college", sort_order=1, school_year="2026-2027"))
        self.db.commit()
        r = self._bulk_create()
        self.assertEqual(len(r.json()["created"]), 18)

    def test_blank_school_year_rejected(self):
        r = self._bulk_create(school_year="   ")
        self.assertEqual(r.status_code, 422)

    def test_writes_single_batch_audit_entry(self):
        self._bulk_create()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "classes_bulk_created")).all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_user_id, self.admin_user.id)
        self.assertEqual(logs[0].new_value["school_year"], SCHOOL_YEAR)
        self.assertEqual(len(logs[0].new_value["created"]), 18)
        self.assertEqual(logs[0].new_value["skipped"], [])

    def test_noop_rerun_writes_no_audit_entry(self):
        self._bulk_create()
        self._bulk_create()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "classes_bulk_created")).all()
        self.assertEqual(len(logs), 1)

    def test_requires_admin(self):
        r = self._bulk_create(headers=self._headers(self.teacher_user.email))
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
