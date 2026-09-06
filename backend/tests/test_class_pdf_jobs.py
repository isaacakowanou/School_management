import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Class,
    Course,
    PdfJob,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentClassAssignment,
    Teacher,
    User,
)

YEAR = "2026-2027"
TERM = "1er Trimestre"


class ClassPdfJobTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-pdfjob@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-pdfjob@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-PDFJOB-1")
        self.db.add(self.teacher)

        self.terminale = Class(name_fr="Terminale C", school_level="college", sort_order=8, school_year=YEAR)
        self.other_class = Class(name_fr="6ème", school_level="college", sort_order=1, school_year=YEAR)
        self.db.add_all([self.terminale, self.other_class])
        self.db.flush()

        self.course = Course(
            name="Mathématique",
            code="PDFJOB-MATH",
            teacher_id=self.teacher.id,
            term=TERM,
            school_year=YEAR,
            language_group="FRENCH",
            class_id=self.terminale.id,
        )
        self.db.add(self.course)

        self.student_a = Student(first_name="Ayo", last_name="Akowanou", student_number="P-001", class_id=self.terminale.id)
        self.student_b = Student(first_name="Bola", last_name="Dossou", student_number="P-002", class_id=self.terminale.id)
        self.student_c = Student(first_name="Chidi", last_name="Hounton", student_number="P-003", class_id=self.terminale.id)
        self.student_other = Student(first_name="Dede", last_name="Gbaguidi", student_number="P-999", class_id=self.other_class.id)
        self.db.add_all([self.student_a, self.student_b, self.student_c, self.student_other])
        self.db.flush()

        self.db.add_all(
            [
                StudentClassAssignment(
                    student_id=student.id,
                    school_year=YEAR,
                    class_id=school_class.id,
                    class_name_snapshot=school_class.name_fr,
                )
                for student, school_class in (
                    (self.student_a, self.terminale),
                    (self.student_b, self.terminale),
                    (self.student_c, self.terminale),
                    (self.student_other, self.other_class),
                )
            ]
        )

        # Two parent-visible reports in the class, one draft (excluded), one
        # approved report in another class (excluded).
        self._add_report(self.student_a, status="sent")
        self._add_report(self.student_b, status="approved")
        self._add_report(self.student_c, status="draft")
        self._add_report(self.student_other, status="approved")
        self.db.commit()

    def _add_report(self, student, *, status):
        report = ReportCard(
            student_id=student.id,
            term=TERM,
            school_year=YEAR,
            overall_average=14.0,
            french_average=14.0,
            english_average=None,
            bilingual_average=None,
            gpa=None,
            scale="20",
            status=status,
        )
        self.db.add(report)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=report.id,
                course_id=self.course.id,
                course_name=self.course.name,
                average=14.0,
                letter_grade="B",
                coefficient=5,
                moy_int=14.0,
                mcc=14.5,
                devoir_score=15.0,
                composition_score=13.0,
            )
        )
        return report

    def _login(self, email) -> dict:
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self) -> dict:
        return self._login("admin-pdfjob@example.test")

    def _payload(self) -> dict:
        return {"class_id": str(self.terminale.id), "school_year": YEAR, "term": TERM}

    def test_job_renders_merged_pdf(self):
        headers = self._admin()
        # The background task opens its own session; point it at the test DB.
        with patch("routes.reports.SessionLocal", self.SessionLocal):
            response = self.client.post("/api/v1/reports/class-pdf", json=self._payload(), headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["job_id"]

        job = self.db.get(PdfJob, __import__("uuid").UUID(job_id))
        self.assertEqual(job.status, "done", job.error)
        # Draft and other-class reports excluded: exactly the 2 parent-visible ones.
        self.assertEqual(job.report_count, 2)
        self.assertIsNotNone(job.pdf_bytes)
        self.assertEqual(job.pdf_bytes[:5], b"%PDF-")

        download = self.client.get(f"/api/v1/reports/class-pdf/{job_id}", headers=headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.headers["content-type"], "application/pdf")
        self.assertIn("Terminale-C", download.headers["content-disposition"])
        self.assertIn("bulletins.pdf", download.headers["content-disposition"])
        self.assertEqual(download.content[:5], b"%PDF-")

    def test_pending_job_returns_json_status(self):
        headers = self._admin()
        with patch("routes.reports._run_class_pdf_job"):
            response = self.client.post("/api/v1/reports/class-pdf", json=self._payload(), headers=headers)
        job_id = response.json()["job_id"]

        poll = self.client.get(f"/api/v1/reports/class-pdf/{job_id}", headers=headers)
        self.assertEqual(poll.status_code, 200)
        self.assertIn("application/json", poll.headers["content-type"])
        self.assertEqual(poll.json()["status"], "pending")

    def test_render_failure_marks_job_failed(self):
        headers = self._admin()
        with (
            patch("routes.reports.SessionLocal", self.SessionLocal),
            patch("routes.reports.render_class_bulletins_pdf_bytes", side_effect=RuntimeError("boom")),
        ):
            response = self.client.post("/api/v1/reports/class-pdf", json=self._payload(), headers=headers)
        job_id = response.json()["job_id"]

        poll = self.client.get(f"/api/v1/reports/class-pdf/{job_id}", headers=headers)
        self.assertIn("application/json", poll.headers["content-type"])
        body = poll.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["error"], "boom")

    def test_400_when_no_visible_reports(self):
        payload = self._payload()
        payload["class_id"] = str(self.other_class.id)
        # other_class has one approved report -> use a term with none instead.
        payload["term"] = "3ème Trimestre"
        response = self.client.post("/api/v1/reports/class-pdf", json=payload, headers=self._admin())
        self.assertEqual(response.status_code, 400)

    def test_requires_admin(self):
        headers = self._login("teacher-pdfjob@example.test")
        response = self.client.post("/api/v1/reports/class-pdf", json=self._payload(), headers=headers)
        self.assertEqual(response.status_code, 403)
        poll = self.client.get(f"/api/v1/reports/class-pdf/{self.terminale.id}", headers=headers)
        self.assertEqual(poll.status_code, 403)

    def test_unknown_job_404(self):
        response = self.client.get(
            "/api/v1/reports/class-pdf/00000000-0000-0000-0000-000000000000", headers=self._admin()
        )
        self.assertEqual(response.status_code, 404)

    def test_old_jobs_cleaned_up_on_create(self):
        old_job = PdfJob(
            class_id=self.terminale.id,
            school_year=YEAR,
            term=TERM,
            status="done",
            pdf_bytes=b"%PDF-old",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        self.db.add(old_job)
        self.db.commit()
        old_id = old_job.id

        with patch("routes.reports._run_class_pdf_job"):
            self.client.post("/api/v1/reports/class-pdf", json=self._payload(), headers=self._admin())

        self.db.expire_all()
        self.assertIsNone(self.db.get(PdfJob, old_id))
        remaining = self.db.scalars(select(PdfJob)).all()
        self.assertEqual(len(remaining), 1)


if __name__ == "__main__":
    unittest.main()
