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


class ReportListRouteTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-list@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-list@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-list@example.test", role="teacher")
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-LIST-1")
        self.student = Student(
            first_name="Ada",
            last_name="Lovelace",
            grade_level="Grade 12",
            student_number="LIST001",
        )
        self.db.add_all([self.parent, self.teacher, self.student])
        self.db.flush()
        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))

        self.course = Course(
            name="Mathematics",
            code="MATH-LIST",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()

        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=92.5,
            gpa=4.0,
            status="approved",
            ai_summary="Strong work.",
        )
        self.db.add(self.report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=self.report_card.id,
                course_id=self.course.id,
                course_name="Mathematics",
                average=92.5,
                letter_grade="A",
            )
        )
        self.db.commit()
        self.db.refresh(self.report_card)

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_admin_report_list_includes_student_display_fields(self):
        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        report = data[0]
        self.assertEqual(report["id"], str(self.report_card.id))
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertEqual(report["student_name"], "Ada Lovelace")
        self.assertEqual(report["student_number"], "LIST001")
        self.assertEqual(report["term"], "Fall")
        self.assertEqual(report["school_year"], "2026-2027")
        self.assertEqual(report["status"], "approved")
        self.assertEqual(report["overall_average"], 92.5)
        self.assertEqual(report["gpa"], 4.0)
        self.assertIn("created_at", report)
        self.assertNotIn("courses", report)

    def test_parent_student_reports_keep_existing_shape(self):
        response = self.client.get(
            f"/api/v1/reports/student/{self.student.id}",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        report = data[0]
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertIn("courses", report)
        self.assertNotIn("student_name", report)
        self.assertNotIn("student_number", report)


if __name__ == "__main__":
    unittest.main()
