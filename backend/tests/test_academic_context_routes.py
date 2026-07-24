import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, Enrollment, ReportCard, Student, StudentClassAssignment, Teacher, TrimesterLock, User


class AcademicContextRouteTests(unittest.TestCase):
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
        self.admin = User(
            name="ZZ-TEST Context Admin",
            email="zz-test-context-admin@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        self.db.add(self.admin)
        self.teacher_user = User(
            name="ZZ-TEST Context Teacher",
            email="zz-test-context-teacher@example.test",
            password_hash=hash_password(self.password),
            role="teacher",
        )
        self.db.add(self.teacher_user)
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-CONTEXT-TCH")
        self.db.add(self.teacher)
        self.db.add_all(
            [
                Class(name_fr="CM2", school_level="primaire", sort_order=6, school_year="2025-2026"),
                Class(name_fr="6ème", school_level="college", sort_order=7, school_year="2026-2027"),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _headers(self) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_current_context_uses_latest_class_year_and_first_unlocked_term(self):
        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["current_school_year"], "2026-2027")
        self.assertEqual(data["current_term"], "1er Trimestre")
        self.assertEqual(data["available_school_years"], ["2026-2027", "2025-2026"])

    def test_course_only_year_is_available_but_not_current(self):
        self.db.add(
            Course(
                name="ZZ-TEST Future Course",
                code="ZZ-TEST-FUTURE-COURSE",
                teacher_id=self.teacher.id,
                term="1er Trimestre",
                school_year="2027-2028",
            )
        )
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["current_school_year"], "2026-2027")
        self.assertIn("2027-2028", data["available_school_years"])

    def test_assignment_year_remains_available_when_class_is_soft_deleted(self):
        student = Student(
            first_name="ZZ-TEST",
            last_name="Assignment Context",
            student_number="ZZ-TEST-ASSIGNMENT-CONTEXT",
        )
        school_class = Class(
            name_fr="Archive Assignment",
            school_level="college",
            sort_order=50,
            school_year="2031-2032",
        )
        self.db.add_all([student, school_class])
        self.db.flush()
        self.db.add(StudentClassAssignment(
            student_id=student.id,
            school_year=school_class.school_year,
            class_id=school_class.id,
            class_name_snapshot=school_class.name_fr,
        ))
        from datetime import datetime, timezone
        school_class.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("2031-2032", response.json()["available_school_years"])
        self.assertEqual(response.json()["current_school_year"], "2026-2027")

    def test_years_from_classes_courses_reports_and_enrollments_are_available(self):
        student = Student(first_name="ZZ-TEST", last_name="Context", student_number="ZZ-TEST-CONTEXT-STU")
        self.db.add(student)
        self.db.flush()
        enrollment_course = Course(
            name="ZZ-TEST Enrollment Course",
            code="ZZ-TEST-ENROLLMENT-COURSE",
            teacher_id=self.teacher.id,
            term="1er Trimestre",
            school_year="2028-2029",
        )
        course_only = Course(
            name="ZZ-TEST Course Only",
            code="ZZ-TEST-COURSE-ONLY",
            teacher_id=self.teacher.id,
            term="1er Trimestre",
            school_year="2029-2030",
        )
        self.db.add_all([enrollment_course, course_only])
        self.db.flush()
        self.db.add(Enrollment(student_id=student.id, course_id=enrollment_course.id))
        self.db.add(
            ReportCard(
                student_id=student.id,
                term="1er Trimestre",
                school_year="2030-2031",
                overall_average=12,
                gpa=2.0,
                status="approved",
            )
        )
        self.db.add(Class(name_fr="CE1", school_level="primaire", sort_order=3, school_year="2031-2032"))
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        years = response.json()["available_school_years"]
        for year in ["2028-2029", "2029-2030", "2030-2031", "2031-2032", "2026-2027", "2025-2026"]:
            self.assertIn(year, years)

    def test_current_term_skips_locked_terms(self):
        self.db.add(
            TrimesterLock(
                school_year="2026-2027",
                term="1er Trimestre",
                is_locked=True,
                updated_by_admin_id=self.admin.id,
            )
        )
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["current_term"], "2ème Trimestre")

    def test_current_term_is_third_when_all_terms_locked(self):
        self.db.add_all(
            [
                TrimesterLock(
                    school_year="2026-2027",
                    term=term,
                    is_locked=True,
                    updated_by_admin_id=self.admin.id,
                )
                for term in ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
            ]
        )
        self.db.commit()

        response = self.client.get("/api/v1/academic-context", headers=self._headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["current_term"], "3ème Trimestre")
