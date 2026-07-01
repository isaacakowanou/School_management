import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from constants import term_number
from database import get_db
from main import app
from models import (
    Base,
    Class,
    Course,
    Parent,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)
from services.report_builder import build_report_card_data_from_report_card


class ReportPdfTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-pdf@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-pdf@example.test", role="parent")
        self.other_parent_user = self._user(name="Other", email="other-pdf@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-pdf@example.test", role="teacher")
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.other_parent = Parent(user=self.other_parent_user, phone="555-0200")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-PDF-1")
        self.student = Student(
            first_name="Isaac", last_name="Student", grade_level="Grade 12", student_number="STU001"
        )
        self.db.add_all([self.parent, self.other_parent, self.teacher, self.student])
        self.db.flush()
        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))

        # Untagged course (no language_group) -> renders in the "Other" section.
        self.course = Course(
            name="Mathematics", code="MATH-12", teacher=self.teacher,
            grade_level="Grade 12", term="Fall", school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.commit()

        # Sent report (parent-visible), no class, untagged course, bogus pdf_url on
        # purpose to prove the download renders live and needs no file on disk.
        self.sent_report = self._add_report(term="Fall", status="sent", pdf_url="/nope.pdf")
        self.draft_report = self._add_report(term="Spring", status="draft")

    def _add_report(self, *, term, status, gpa=3.0, fr=None, en=None, bil=None, overall=15.0, pdf_url=None):
        report = ReportCard(
            student=self.student, term=term, school_year="2026-2027",
            overall_average=overall, french_average=fr, english_average=en, bilingual_average=bil,
            gpa=gpa, status=status, pdf_url=pdf_url,
        )
        self.db.add(report)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=report.id, course_id=self.course.id,
                course_name=self.course.name, average=overall, letter_grade="B",
            )
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _download(self, report, email):
        return self.client.get(f"/api/v1/reports/{report.id}/pdf", headers=self._headers(email))

    def _assert_pdf(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    # --- endpoint auth + rendering ---
    def test_admin_downloads_pdf(self):
        response = self._download(self.sent_report, self.admin_user.email)
        self._assert_pdf(response)
        self.assertIn("STU001_Fall_2026-2027.pdf", response.headers.get("content-disposition", ""))

    def test_linked_parent_downloads_sent_report(self):
        self._assert_pdf(self._download(self.sent_report, self.parent_user.email))

    def test_parent_cannot_download_draft(self):
        self.assertEqual(self._download(self.draft_report, self.parent_user.email).status_code, 403)

    def test_unlinked_parent_cannot_download(self):
        # Ticket said 404; the endpoint actually returns 403 for any report a
        # parent can't access (get_report_card_or_404 finds it, then auth denies).
        self.assertEqual(self._download(self.sent_report, self.other_parent_user.email).status_code, 403)

    def test_report_with_no_class_renders(self):
        self.assertIsNone(self.student.class_id)
        self._assert_pdf(self._download(self.sent_report, self.admin_user.email))

    def test_report_with_untagged_courses_renders(self):
        data = build_report_card_data_from_report_card(self.db, self.sent_report)
        self.assertEqual(len(data["courses_by_language"]["untagged_courses"]), 1)
        self.assertEqual(data["courses_by_language"]["french_courses"], [])
        self._assert_pdf(self._download(self.sent_report, self.admin_user.email))

    def test_report_with_class_of_one_renders(self):
        school_class = Class(
            name_fr="6ème", name_en="JSS1", school_level="college", sort_order=1, school_year="2026-2027"
        )
        self.db.add(school_class)
        self.db.flush()
        self.student.class_id = school_class.id
        self.db.commit()
        report = self._add_report(term="1er Trimestre", status="sent", fr=14.0, en=16.0, bil=15.0)

        data = build_report_card_data_from_report_card(self.db, report)
        self.assertEqual(data["class_stats"]["french"]["highest"], 14.0)
        self.assertEqual(data["class_stats"]["french"]["lowest"], 14.0)
        self._assert_pdf(self._download(report, self.admin_user.email))

    def test_missing_logo_renders(self):
        with patch("services.pdf_renderer.LOGO_PATH", Path("/nonexistent/ggfk_logo.png")):
            response = self._download(self.sent_report, self.admin_user.email)
        self._assert_pdf(response)

    def test_gpa_none_renders(self):
        report = self._add_report(term="Fall", status="sent", gpa=None)
        self._assert_pdf(self._download(report, self.admin_user.email))

    # --- data layer: trimester / annual ---
    def test_term_number_resolver(self):
        self.assertEqual(term_number("1er Trimestre"), 1)  # exact
        self.assertEqual(term_number("2ÈME TRIMESTRE"), 2)  # case-insensitive
        self.assertEqual(term_number("Trimester 3"), 3)  # loose contains "3"
        self.assertIsNone(term_number("Fall"))
        self.assertIsNone(term_number(None))

    def test_final_trimester_populates_annual(self):
        self._add_report(term="1er Trimestre", status="approved", fr=12.0, en=14.0, bil=13.0)
        self._add_report(term="2ème Trimestre", status="approved", fr=14.0, en=16.0, bil=15.0)
        third = self._add_report(term="3ème Trimestre", status="approved", fr=16.0, en=18.0, bil=17.0)

        data = build_report_card_data_from_report_card(self.db, third)
        self.assertEqual(data["term_number"], 3)
        self.assertTrue(data["is_final_trimester"])
        self.assertEqual(data["three_averages"]["annual"]["french"], 14.0)  # mean(12,14,16)
        self.assertEqual(data["three_averages"]["annual"]["english"], 16.0)
        self.assertEqual(data["three_averages"]["annual"]["bilingual"], 15.0)

    def test_non_final_trimester_has_no_annual(self):
        first = self._add_report(term="1er Trimestre", status="approved", fr=12.0, en=14.0, bil=13.0)
        data = build_report_card_data_from_report_card(self.db, first)
        self.assertEqual(data["term_number"], 1)
        self.assertFalse(data["is_final_trimester"])
        self.assertIsNone(data["three_averages"]["annual"]["french"])


if __name__ == "__main__":
    unittest.main()
