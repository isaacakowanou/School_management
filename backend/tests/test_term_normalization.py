"""A1.7c — canonical trimester terms.

Covers the four layers: the variant normalizer in constants, write-path
validation (courses / grade items / report generation), the data migration
that normalizes legacy rows, and the report builder picking up a course
result once its term is normalized.
"""
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alembic import command as alembic_command
from alembic.config import Config

from auth import hash_password
from constants import TRIMESTER_TERMS, normalize_term
from database import get_db
from main import app
from models import Base, Course, CourseResult, GradeItem, Student, Teacher, User
from services.report_builder import build_report_card_data

_ALEMBIC_INI = str(Path(__file__).parent.parent / "alembic.ini")
_PREV_REV = "d7a4c9e2f6b1"
_THIS_REV = "e5c2a8b7d4f9"


class NormalizeTermTests(unittest.TestCase):
    def test_canonical_values_pass_through(self):
        for term in TRIMESTER_TERMS:
            self.assertEqual(normalize_term(term), term)

    def test_variant_table(self):
        cases = {
            "1er Trimestre": ["Fall", "fall", "FALL", "Trimester 1", "Trimestre 1", "1e Trimestre", "Term 1", "1st Term", "1er"],
            "2ème Trimestre": ["Spring", "spring", "Trimester 2", "Trimestre 2", "2e Trimestre", "Term 2", "2nd Term", "2ème", "2eme"],
            "3ème Trimestre": ["Summer", "SUMMER", "Trimester 3", "Trimestre 3", "3e Trimestre", "Term 3", "3rd Term", "3ème", "3eme"],
        }
        for canonical, variants in cases.items():
            for variant in variants:
                self.assertEqual(normalize_term(variant), canonical, variant)

    def test_accent_case_whitespace_insensitive(self):
        self.assertEqual(normalize_term("  1ER   TRIMESTRE "), "1er Trimestre")
        self.assertEqual(normalize_term("2ÈME TRIMESTRE"), "2ème Trimestre")

    def test_unrecognized_returns_none(self):
        for value in ("Fall 2026", "Semester 1", "Q1", "", None, "Winter"):
            self.assertIsNone(normalize_term(value), value)


class TermValidationTests(unittest.TestCase):
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

        self.admin_user = User(
            name="Admin", email="admin-term@example.test", password_hash=hash_password(self.password), role="admin"
        )
        self.db.add(self.admin_user)
        self.db.flush()
        self.teacher = Teacher(
            user=User(
                name="Teacher", email="teacher-term@example.test", password_hash=hash_password(self.password), role="teacher"
            ),
            employee_number="T-TERM-1",
        )
        self.db.add(self.teacher)
        self.student = Student(first_name="Ama", last_name="Kow", grade_level="6ème", student_number="S-TERM-1")
        self.db.add(self.student)
        self.course = Course(
            name="Maths", code="TERM-M1", teacher=self.teacher, grade_level="6ème",
            term="1er Trimestre", school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _admin(self):
        r = self.client.post(
            "/api/v1/auth/login", json={"email": self.admin_user.email, "password": self.password}
        )
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _course_payload(self, term):
        return {
            "name": "New Course",
            "code": "TERM-NEW",
            "teacher_id": str(self.teacher.id),
            "grade_level": "6ème",
            "term": term,
            "school_year": "2026-2027",
        }

    def test_course_create_rejects_free_text_terms(self):
        for term in ("Fall", "Trimester 1", "  1er Trimestre  ", "whatever"):
            r = self.client.post("/api/v1/courses", json=self._course_payload(term), headers=self._admin())
            self.assertEqual(r.status_code, 422, term)

    def test_course_create_accepts_canonical_term(self):
        r = self.client.post(
            "/api/v1/courses", json=self._course_payload("2ème Trimestre"), headers=self._admin()
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["term"], "2ème Trimestre")

    def test_course_update_rejects_free_text_term(self):
        r = self.client.put(
            f"/api/v1/courses/{self.course.id}", json={"term": "Spring"}, headers=self._admin()
        )
        self.assertEqual(r.status_code, 422)

    def test_grade_item_create_rejects_free_text_term(self):
        payload = {
            "course_id": str(self.course.id),
            "title": "Devoir",
            "category": "test",
            "max_score": 20,
            "weight": 1.0,
            "term": "Fall",
        }
        r = self.client.post("/api/v1/grade-items", json=payload, headers=self._admin())
        self.assertEqual(r.status_code, 422)

        payload["term"] = "1er Trimestre"
        r = self.client.post("/api/v1/grade-items", json=payload, headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)

    def test_report_generation_rejects_free_text_term(self):
        r = self.client.post(
            f"/api/v1/reports/generate/{self.student.id}",
            json={"term": "Fall", "school_year": "2026-2027"},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 422)

    def test_report_generation_accepts_canonical_term(self):
        # Canonical term passes validation; the 400 comes from the builder
        # (no course results yet), proving we got past the 422 layer.
        r = self.client.post(
            f"/api/v1/reports/generate/{self.student.id}",
            json={"term": "1er Trimestre", "school_year": "2026-2027"},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 400)


class TermMigrationTests(unittest.TestCase):
    """Data-migration test on a throwaway SQLite DB (same pattern as e7f2d9c1b8a3)."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_url = f"sqlite:///{self.db_path}"
        self._orig_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.db_url
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", self.db_url)
        self.cfg = cfg

        alembic_command.upgrade(self.cfg, _PREV_REV)

        self.engine = create_engine(self.db_url)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, name, email, password_hash, role) VALUES ('u1','T','t@t.com','h','teacher')"))
            conn.execute(text("INSERT INTO teachers (id, user_id, employee_number) VALUES ('t1','u1','E001')"))
            conn.execute(text("INSERT INTO students (id, first_name, last_name, grade_level, student_number) VALUES ('s1','A','B','6ème','S001')"))
            # One row per legacy shape, spread across the four term tables.
            conn.execute(text(
                "INSERT INTO courses (id, name, code, teacher_id, grade_level, term, school_year)"
                " VALUES ('c1','Math','M01','t1','6ème','Fall','2026-2027'),"
                "        ('c2','Eng','E01','t1','6ème','Trimester 1','2026-2027'),"
                "        ('c3','Sci','S01','t1','6ème','Fall 2026','2026-2027'),"
                "        ('c4','Art','A01','t1','6ème','1er Trimestre','2026-2027')"
            ))
            conn.execute(text(
                "INSERT INTO grade_items (id, course_id, title, category, max_score, weight, term)"
                " VALUES ('gi1','c1','HW','HW',20,1.0,'Spring')"
            ))
            conn.execute(text(
                "INSERT INTO course_results (id, student_id, course_id, term, average, letter_grade)"
                " VALUES ('cr1','s1','c1','Summer',12.0,'C+')"
            ))
            # Collision pair: same student+course holds a result under a legacy
            # spelling AND its canonical form (the real-world incident shape).
            conn.execute(text(
                "INSERT INTO course_results (id, student_id, course_id, term, average, letter_grade)"
                " VALUES ('cr2','s1','c2','Fall',10.0,'C'),"
                "        ('cr3','s1','c2','1er Trimestre',15.0,'B+')"
            ))
            conn.execute(text(
                "INSERT INTO report_cards (id, student_id, term, school_year, overall_average, status)"
                " VALUES ('r1','s1','Trimester 2','2026-2027',12.0,'draft')"
            ))

    def tearDown(self):
        self.engine.dispose()
        if self._orig_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._orig_db_url
        os.unlink(self.db_path)

    def test_migration_normalizes_recognized_and_preserves_unrecognized(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)

        with self.engine.connect() as conn:
            course_terms = dict(conn.execute(text("SELECT id, term FROM courses")).all())
            self.assertEqual(course_terms["c1"], "1er Trimestre")  # Fall
            self.assertEqual(course_terms["c2"], "1er Trimestre")  # Trimester 1
            self.assertEqual(course_terms["c3"], "Fall 2026")  # unrecognized: untouched
            self.assertEqual(course_terms["c4"], "1er Trimestre")  # already canonical

            self.assertEqual(
                conn.execute(text("SELECT term FROM grade_items WHERE id='gi1'")).scalar(),
                "2ème Trimestre",  # Spring
            )
            self.assertEqual(
                conn.execute(text("SELECT term FROM course_results WHERE id='cr1'")).scalar(),
                "3ème Trimestre",  # Summer
            )
            # Collision pair: the legacy row is skipped (canonical twin exists),
            # the canonical row is untouched — no constraint violation.
            self.assertEqual(
                conn.execute(text("SELECT term FROM course_results WHERE id='cr2'")).scalar(),
                "Fall",
            )
            self.assertEqual(
                conn.execute(text("SELECT term FROM course_results WHERE id='cr3'")).scalar(),
                "1er Trimestre",
            )
            self.assertEqual(
                conn.execute(text("SELECT term FROM report_cards WHERE id='r1'")).scalar(),
                "2ème Trimestre",  # Trimester 2
            )


class ReportBuilderPickupTests(unittest.TestCase):
    """A course result invisible under a legacy term is found once normalized."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        teacher = Teacher(
            user=User(name="T", email="t-pickup@example.test", password_hash="h", role="teacher"),
            employee_number="T-PICK-1",
        )
        self.db.add(teacher)
        self.student = Student(first_name="Ama", last_name="Kow", grade_level="6ème", student_number="S-PICK-1")
        self.db.add(self.student)
        course = Course(
            name="Maths", code="PICK-M1", teacher=teacher, grade_level="6ème",
            term="Trimester 1", school_year="2026-2027", language_group="FRENCH",
        )
        self.db.add(course)
        self.db.flush()
        self.db.add(
            CourseResult(
                student_id=self.student.id, course_id=course.id, term="Trimester 1",
                average=14.0, letter_grade="B", scale="20",
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_result_invisible_before_normalization_found_after(self):
        with self.assertRaisesRegex(ValueError, "no course results"):
            build_report_card_data(self.db, self.student.id, "1er Trimestre", "2026-2027")

        # Normalize the way the migration does, through the same helper.
        for result in self.db.scalars(select(CourseResult)).all():
            canonical = normalize_term(result.term)
            if canonical is not None:
                result.term = canonical
        self.db.commit()

        report_data = build_report_card_data(self.db, self.student.id, "1er Trimestre", "2026-2027")
        self.assertEqual(report_data["term"], "1er Trimestre")
        self.assertEqual(len(report_data["courses"]), 1)
        self.assertEqual(report_data["courses"][0]["average"], 14.0)


if __name__ == "__main__":
    unittest.main()
