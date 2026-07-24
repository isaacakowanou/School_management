import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, CourseResult, ReportCard, ReportCardCourse, Student, Teacher, User


SOURCE_YEAR = "2026-2027"
TARGET_YEAR = "2027-2028"
PASSWORD = "test-password-123"


class SchoolYearRolloverArchiveTests(unittest.TestCase):
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

    def _seed(self):
        self.admin_user = User(
            name="ZZ-TEST Rollover Admin",
            email="zz-test-rollover-admin@example.test",
            password_hash=hash_password(PASSWORD),
            role="admin",
        )
        self.teacher_user = User(
            name="ZZ-TEST Rollover Teacher",
            email="zz-test-rollover-teacher@example.test",
            password_hash=hash_password(PASSWORD),
            role="teacher",
        )
        self.db.add_all([self.admin_user, self.teacher_user])
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-ROLLOVER-TCH")
        self.source_class = Class(
            name_fr="6ème",
            school_level="college",
            sort_order=7,
            school_year=SOURCE_YEAR,
        )
        self.db.add_all([self.teacher, self.source_class])
        self.db.flush()
        self.source_course = Course(
            name="Mathématique",
            code="ZZ-TEST-ROLLOVER-MATH",
            teacher_id=self.teacher.id,
            term="3ème Trimestre",
            school_year=SOURCE_YEAR,
            language_group="FRENCH",
            class_id=self.source_class.id,
            coefficient=4,
            grading_system="BENINESE",
        )
        self.student = Student(
            first_name="ZZ-TEST",
            last_name="Archive",
            student_number="ZZ-TEST-ARCHIVE-STU",
            school_class=self.source_class,
        )
        self.graduated_student = Student(
            first_name="ZZ-TEST",
            last_name="Graduated Archive",
            student_number="ZZ-TEST-ARCHIVE-GRAD",
            academic_status="graduated",
        )
        self.db.add_all([self.source_course, self.student, self.graduated_student])
        self.db.flush()
        self.result = CourseResult(
            student=self.student,
            course=self.source_course,
            term="3ème Trimestre",
            average=15,
            letter_grade="A",
            scale="20",
            calculated_at=datetime.now(timezone.utc),
        )
        self.report = ReportCard(
            student=self.student,
            term="3ème Trimestre",
            school_year=SOURCE_YEAR,
            overall_average=15,
            french_average=15,
            gpa=4.0,
            scale="20",
            status="approved",
            approved_by_admin=self.admin_user,
            approved_at=datetime.now(timezone.utc),
        )
        self.db.add_all([self.result, self.report])
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card=self.report,
                course=self.source_course,
                course_name=self.source_course.name,
                average=15,
                letter_grade="A",
                coefficient=4,
            )
        )
        self.db.commit()

    def _headers(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin_user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_new_school_year_creates_classes_clones_courses_and_updates_context(self):
        response = self.client.post(
            "/api/v1/school-years",
            json={
                "school_year": TARGET_YEAR,
                "clone_courses": True,
                "source_school_year": SOURCE_YEAR,
            },
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["school_year"], TARGET_YEAR)
        self.assertEqual(len(body["created_classes"]), 18)
        self.assertEqual(body["cloned_course_count"], 1)
        self.assertEqual(body["skipped_course_count"], 0)
        self.assertFalse(body["nothing_to_do"])

        clone = self.db.scalar(select(Course).where(Course.code == f"{self.source_course.code}-{TARGET_YEAR}"))
        self.assertIsNotNone(clone)
        self.assertEqual(clone.grading_system, "BENINESE")
        self.assertEqual(clone.coefficient, 4)
        self.assertEqual(clone.term, "1er Trimestre")
        self.assertEqual(clone.school_year, TARGET_YEAR)
        self.assertIsNotNone(clone.class_id)

        context = self.client.get("/api/v1/academic-context", headers=self._headers())
        self.assertEqual(context.status_code, 200, context.text)
        self.assertEqual(context.json()["current_school_year"], TARGET_YEAR)
        self.assertIn(TARGET_YEAR, context.json()["available_school_years"])

    def test_complete_partial_course_only_year_fills_missing_setup_without_409(self):
        self.db.add(
            Course(
                name="Existing partial course",
                code="ZZ-TEST-PARTIAL-EXISTING",
                teacher_id=self.teacher.id,
                term="1er Trimestre",
                school_year=TARGET_YEAR,
            )
        )
        self.db.commit()

        response = self.client.post(
            "/api/v1/school-years",
            json={
                "school_year": TARGET_YEAR,
                "clone_courses": True,
                "source_school_year": SOURCE_YEAR,
            },
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(len(body["created_classes"]), 18)
        self.assertEqual(body["cloned_course_count"], 1)
        self.assertEqual(body["skipped_course_count"], 0)
        self.assertFalse(body["nothing_to_do"])
        self.assertIsNotNone(
            self.db.scalar(select(Course).where(Course.code == f"{self.source_course.code}-{TARGET_YEAR}"))
        )

    def test_complete_school_year_twice_is_idempotent(self):
        first = self.client.post(
            "/api/v1/school-years",
            json={
                "school_year": TARGET_YEAR,
                "clone_courses": True,
                "source_school_year": SOURCE_YEAR,
            },
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 201, first.text)

        second = self.client.post(
            "/api/v1/school-years",
            json={
                "school_year": TARGET_YEAR,
                "clone_courses": True,
                "source_school_year": SOURCE_YEAR,
            },
            headers=self._headers(),
        )

        self.assertEqual(second.status_code, 201, second.text)
        body = second.json()
        self.assertEqual(body["created_classes"], [])
        self.assertEqual(len(body["skipped_classes"]), 18)
        self.assertEqual(body["cloned_course_count"], 0)
        self.assertEqual(body["skipped_course_count"], 1)
        self.assertTrue(body["nothing_to_do"])

    def test_archives_return_past_records_and_regenerate_uses_existing_lifecycle(self):
        self.client.post(
            "/api/v1/school-years",
            json={"school_year": TARGET_YEAR, "clone_courses": False},
            headers=self._headers(),
        )

        reports = self.client.get("/api/v1/archives/reports", headers=self._headers())
        courses = self.client.get("/api/v1/archives/courses", headers=self._headers())
        students = self.client.get("/api/v1/archives/students", headers=self._headers())

        self.assertEqual(reports.status_code, 200, reports.text)
        self.assertEqual(courses.status_code, 200, courses.text)
        self.assertEqual(students.status_code, 200, students.text)
        self.assertEqual([item["id"] for item in reports.json()], [str(self.report.id)])
        self.assertEqual([item["id"] for item in courses.json()], [str(self.source_course.id)])
        self.assertEqual([item["id"] for item in students.json()], [str(self.graduated_student.id)])

        regenerate = self.client.post(f"/api/v1/reports/{self.report.id}/regenerate", headers=self._headers())

        self.assertEqual(regenerate.status_code, 200, regenerate.text)
        self.assertEqual(regenerate.json()["status"], "draft")
        self.assertEqual(regenerate.json()["school_year"], SOURCE_YEAR)
