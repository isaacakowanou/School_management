import contextlib
import io
import unittest

from sqlalchemy import create_engine, text

from scripts import count_legacy_terms


class CountLegacyTermsScriptTests(unittest.TestCase):
    def test_reports_legacy_values_without_writing(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE course_results (id INTEGER PRIMARY KEY, term TEXT NOT NULL)"))
            connection.execute(text("CREATE TABLE pdf_jobs (id INTEGER PRIMARY KEY, term TEXT NOT NULL)"))
            connection.execute(
                text("INSERT INTO course_results (term) VALUES ('1er Trimestre'), ('Trimester 1'), ('Trimester 1')")
            )
            connection.execute(text("INSERT INTO pdf_jobs (term) VALUES ('2ème Trimestre'), ('Spring')"))

        original_engine = count_legacy_terms.engine
        count_legacy_terms.engine = engine
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                count_legacy_terms.main()
        finally:
            count_legacy_terms.engine = original_engine

        report = output.getvalue()
        self.assertIn("course_results.term: total=3, non_canonical=2", report)
        self.assertIn("'Trimester 1': 2 -> recognized as '1er Trimestre'", report)
        self.assertIn("'Spring': 1 -> recognized as '2ème Trimestre'", report)
        self.assertIn("READ-ONLY — no changes made", report)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM course_results")).scalar_one(), 3)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM pdf_jobs")).scalar_one(), 2)
        engine.dispose()
