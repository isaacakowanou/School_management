import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Course,
    Parent,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)


class ReportPdfDownloadTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-pdf.test@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-pdf.test@example.test", role="parent")
        self.other_parent_user = self._user(
            name="Other Parent", email="other-pdf.test@example.test", role="parent"
        )
        self.teacher_user = self._user(name="Teacher", email="teacher-pdf.test@example.test", role="teacher")
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.other_parent = Parent(user=self.other_parent_user, phone="555-0200")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-PDF-1")
        self.student = Student(
            first_name="Isaac",
            last_name="Student",
            grade_level="Grade 12",
            student_number="STU001",
        )
        self.db.add_all([self.parent, self.other_parent, self.teacher, self.student])
        self.db.flush()

        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))
        self.course = Course(
            name="Mathematics",
            code="MATH-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()

        # Approved report with a deliberately bogus pdf_url to prove download no
        # longer depends on a file existing on disk.
        self.approved = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=91.7,
            gpa=4.0,
            status="approved",
            ai_summary="Great term.",
            pdf_url="/nonexistent/path/report.pdf",
        )
        self.db.add(self.approved)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=self.approved.id,
                course_id=self.course.id,
                course_name="Mathematics",
                average=91.7,
                letter_grade="A",
            )
        )

        # Draft report — parents must not be able to download it.
        self.draft = ReportCard(
            student=self.student,
            term="Spring",
            school_year="2026-2027",
            overall_average=80.0,
            gpa=3.0,
            status="draft",
        )
        self.db.add(self.draft)
        self.db.commit()
        self.db.refresh(self.approved)
        self.db.refresh(self.draft)

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": self.password}
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_admin_downloads_pdf_without_file_on_disk(self):
        response = self.client.get(
            f"/api/v1/reports/{self.approved.id}/pdf",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(
            "STU001_Fall_2026-2027.pdf", response.headers.get("content-disposition", "")
        )

    def test_linked_parent_downloads_approved_report(self):
        response = self.client.get(
            f"/api/v1/reports/{self.approved.id}/pdf",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_parent_cannot_download_draft_report(self):
        response = self.client.get(
            f"/api/v1/reports/{self.draft.id}/pdf",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_unlinked_parent_cannot_download(self):
        response = self.client.get(
            f"/api/v1/reports/{self.approved.id}/pdf",
            headers=self._headers(self.other_parent_user.email),
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
