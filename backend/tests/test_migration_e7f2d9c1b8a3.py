"""Tests for Alembic migration e7f2d9c1b8a3: convert /100 grade items to /20.

Each test gets its own temporary SQLite DB, brought up to the revision
immediately before ours (c8f5b2a9d6e1), seeded with representative data, then
upgraded / downgraded as needed.

Coverage:
  - max_score=100 GradeItems are converted to 20
  - Associated Grade.score values are scaled by × 0.2 with rounding
  - Grade items with max_score != 100 (e.g. 50) are left alone
  - The migration SQL is NULL-safe for score (SQL expression verified directly)
  - The migration is idempotent — re-running the SQL finds no max_score=100 rows
  - Downgrade reverses GradeItem.max_score and Grade.score (× 5)
  - Calculator sanity: post-migration /20 data still flows through the grade
    calculator correctly (guard against A1.2.1 accidentally breaking it)
"""
import os
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

from alembic import command as alembic_command
from alembic.config import Config

_ALEMBIC_INI = str(Path(__file__).parent.parent / "alembic.ini")
_PREV_REV = "c8f5b2a9d6e1"
_THIS_REV = "e7f2d9c1b8a3"

# Raw SQL from the migration's upgrade(), reproduced here so the idempotency
# test can re-run it without going through Alembic's version tracking.
_UPGRADE_GRADES_SQL = (
    "UPDATE grades"
    "   SET score = ROUND(CAST(score * 0.2 AS NUMERIC), 2)"
    " WHERE score IS NOT NULL"
    "   AND grade_item_id IN (SELECT id FROM grade_items WHERE max_score = 100)"
)
_UPGRADE_ITEMS_SQL = "UPDATE grade_items SET max_score = 20 WHERE max_score = 100"


def _make_cfg(db_url: str) -> Config:
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


class MigrationE7f2d9c1b8a3Tests(unittest.TestCase):
    """Data-migration tests run against a fresh throwaway SQLite DB per test."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_url = f"sqlite:///{self.db_path}"

        # alembic/env.py reads DATABASE_URL; point it at the temp DB.
        self._orig_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.db_url

        self.cfg = _make_cfg(self.db_url)

        # Bring the schema to the revision just before ours.
        alembic_command.upgrade(self.cfg, _PREV_REV)

        # Seed representative rows via raw SQL.
        engine = create_engine(self.db_url)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (id, name, email, password_hash, role)"
                " VALUES ('u1','T','t@t.com','h','teacher')"
            ))
            conn.execute(text(
                "INSERT INTO teachers (id, user_id, employee_number)"
                " VALUES ('t1','u1','E001')"
            ))
            conn.execute(text(
                "INSERT INTO courses"
                " (id, name, code, teacher_id, grade_level, term, school_year)"
                " VALUES ('c1','Math','M01','t1','12','Fall','2026-2027')"
            ))
            conn.execute(text(
                "INSERT INTO students"
                " (id, first_name, last_name, grade_level, student_number)"
                " VALUES ('s1','A','B','12','S001')"
            ))

            # Two /100 grade items — must be converted.
            conn.execute(text(
                "INSERT INTO grade_items"
                " (id, course_id, title, category, max_score, weight, term)"
                " VALUES ('gi1','c1','Homework','HW',100,0.3,'Fall')"
            ))
            conn.execute(text(
                "INSERT INTO grade_items"
                " (id, course_id, title, category, max_score, weight, term)"
                " VALUES ('gi2','c1','Final','FN',100,0.4,'Fall')"
            ))
            # One /50 grade item — must NOT be touched.
            conn.execute(text(
                "INSERT INTO grade_items"
                " (id, course_id, title, category, max_score, weight, term)"
                " VALUES ('gi3','c1','Bonus','BN',50,0.3,'Fall')"
            ))

            # Grades for the /100 items.
            conn.execute(text(
                "INSERT INTO grades"
                " (id, student_id, grade_item_id, score, submitted_by_teacher_id)"
                " VALUES ('gr1','s1','gi1',92.5,'t1')"
            ))
            conn.execute(text(
                "INSERT INTO grades"
                " (id, student_id, grade_item_id, score, submitted_by_teacher_id)"
                " VALUES ('gr2','s1','gi2',88.0,'t1')"
            ))
            # Grade for the /50 item — score and item must stay unchanged.
            conn.execute(text(
                "INSERT INTO grades"
                " (id, student_id, grade_item_id, score, submitted_by_teacher_id)"
                " VALUES ('gr3','s1','gi3',45.0,'t1')"
            ))
        engine.dispose()

    def tearDown(self):
        if self._orig_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._orig_db_url
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read(self) -> tuple[dict, dict]:
        """Return (grade_item max_scores, grade scores) keyed by id."""
        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            items = {
                r[0]: r[1]
                for r in conn.execute(
                    text("SELECT id, max_score FROM grade_items ORDER BY id")
                ).fetchall()
            }
            scores = {
                r[0]: r[1]
                for r in conn.execute(
                    text("SELECT id, score FROM grades ORDER BY id")
                ).fetchall()
            }
        engine.dispose()
        return items, scores

    # ------------------------------------------------------------------
    # Upgrade tests
    # ------------------------------------------------------------------

    def test_max_score_100_grade_items_convert_to_20(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)
        items, _ = self._read()
        self.assertEqual(items["gi1"], 20)
        self.assertEqual(items["gi2"], 20)

    def test_grade_scores_scaled_by_0_2_with_rounding(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)
        _, scores = self._read()
        self.assertAlmostEqual(scores["gr1"], 18.5, places=2)   # 92.5 × 0.2
        self.assertAlmostEqual(scores["gr2"], 17.6, places=2)   # 88.0 × 0.2

    def test_non_100_max_score_item_and_its_grade_left_unchanged(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)
        items, scores = self._read()
        self.assertEqual(items["gi3"], 50)
        self.assertAlmostEqual(scores["gr3"], 45.0, places=2)

    def test_null_score_sql_expression_is_null_safe(self):
        # Grade.score is NOT NULL in the schema, so null-score rows cannot be
        # seeded normally.  Verify the SQL expression used in the migration is
        # NULL-safe: ROUND(CAST(NULL * 0.2 AS NUMERIC), 2) must return NULL,
        # not raise an error — guarding against rows inserted by direct DB
        # manipulation that bypasses the ORM constraint.
        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT ROUND(CAST(NULL * 0.2 AS NUMERIC), 2)")
            ).scalar()
        engine.dispose()
        self.assertIsNone(result)

    def test_migration_sql_is_idempotent(self):
        # After the first upgrade no rows have max_score=100, so re-running the
        # SQL directly (bypassing Alembic's version tracking) must be a no-op.
        alembic_command.upgrade(self.cfg, _THIS_REV)
        items_first, scores_first = self._read()

        engine = create_engine(self.db_url)
        with engine.begin() as conn:
            conn.execute(text(_UPGRADE_GRADES_SQL))
            conn.execute(text(_UPGRADE_ITEMS_SQL))
        engine.dispose()

        items_second, scores_second = self._read()
        self.assertEqual(items_first, items_second)
        for key in scores_first:
            self.assertAlmostEqual(scores_first[key], scores_second[key], places=5)

    # ------------------------------------------------------------------
    # Downgrade tests
    # ------------------------------------------------------------------

    def test_downgrade_reverses_grade_item_max_scores(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)
        alembic_command.downgrade(self.cfg, _PREV_REV)
        items, _ = self._read()
        self.assertEqual(items["gi1"], 100)
        self.assertEqual(items["gi2"], 100)
        # gi3 had max_score=50 which downgrade doesn't touch (50 ≠ 20).
        self.assertEqual(items["gi3"], 50)

    def test_downgrade_reverses_grade_scores(self):
        alembic_command.upgrade(self.cfg, _THIS_REV)
        alembic_command.downgrade(self.cfg, _PREV_REV)
        _, scores = self._read()
        self.assertAlmostEqual(scores["gr1"], 92.5, places=2)   # 18.5 × 5
        self.assertAlmostEqual(scores["gr2"], 88.0, places=2)   # 17.6 × 5
        # gr3's parent (gi3, max_score=50) is unaffected by downgrade — stays 45.
        self.assertAlmostEqual(scores["gr3"], 45.0, places=2)


class CalculatorSanityAfterMigrationTests(unittest.TestCase):
    """Sanity-check that A1.2.1 didn't break the grade calculator.

    The migration converts existing data to max_score=20.  These tests confirm
    the calculator still handles /20 inputs correctly — complementing
    test_grade_calculator.py with post-migration shapes.
    """

    def test_migrated_scores_produce_correct_course_average(self):
        from services.grade_calculator import calculate_course_average
        # gr1 and gr2 after migration: 18.5/20 and 17.6/20 at equal weight
        grades = [
            {"score": 18.5, "max_score": 20, "weight": 0.5},
            {"score": 17.6, "max_score": 20, "weight": 0.5},
        ]
        avg = calculate_course_average(grades)
        # (18.5/20*20*0.5 + 17.6/20*20*0.5) = (18.5+17.6)/2 = 18.05
        self.assertAlmostEqual(avg, 18.05, places=2)

    def test_migrated_score_yields_correct_letter_grade(self):
        from services.grade_calculator import get_letter_grade
        # 18.5 /20 → BISC: 17 ≤ 18.5 < 19 → "A"
        self.assertEqual(get_letter_grade(18.5), "A")
        # 17.6 /20 → BISC: 17 ≤ 17.6 < 19 → "A"
        self.assertEqual(get_letter_grade(17.6), "A")

    def test_non_100_max_score_still_normalised_correctly(self):
        # gr3: 45/50 — untouched by A1.2.1; Option B normalises it at query time.
        from services.grade_calculator import calculate_course_average
        grades = [{"score": 45.0, "max_score": 50, "weight": 1.0}]
        avg = calculate_course_average(grades)
        # 45/50 * 20 = 18.0
        self.assertAlmostEqual(avg, 18.0, places=2)


if __name__ == "__main__":
    unittest.main()
