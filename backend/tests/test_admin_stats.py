import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, CourseResult, Grade, GradeItem, Parent, ReportCard, Student, Teacher, User


class AdminStatsTests(unittest.TestCase):
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
        self._seed_users()

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

    def _seed_users(self):
        self.admin_user = self._user(name="Admin", email="admin-stats@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-stats@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-stats@example.test", role="teacher")
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="555-1000")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-STATS-1")
        self.db.add_all([self.parent, self.teacher])
        self.db.commit()

    def _headers(self, email):
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin_user.email)

    def test_admin_stats_requires_admin(self):
        self.assertEqual(self.client.get("/api/v1/admin/stats").status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/admin/stats", headers=self._headers(self.parent_user.email)).status_code,
            403,
        )

    def test_counts_exclude_deleted_and_current_term_uses_latest_activity(self):
        deleted_at = datetime.now(timezone.utc)
        school_class = Class(
            name_fr="6ème", name_en="JSS1", school_level="college", sort_order=1, school_year="2026-2027"
        )
        deleted_class = Class(
            name_fr="5ème",
            name_en="JSS2",
            school_level="college",
            sort_order=2,
            school_year="2026-2027",
            deleted_at=deleted_at,
        )
        student = Student(first_name="Ada", last_name="Kou", student_number="S-STATS-1", school_class=school_class)
        deleted_student = Student(
            first_name="Deleted", last_name="Student", student_number="S-STATS-DEL", deleted_at=deleted_at
        )
        deleted_teacher_user = self._user(name="Deleted Teacher", email="deleted-teacher-stats@example.test", role="teacher")
        deleted_parent_user = self._user(name="Deleted Parent", email="deleted-parent-stats@example.test", role="parent")
        self.db.flush()
        deleted_teacher = Teacher(
            user=deleted_teacher_user, employee_number="T-STATS-DEL", deleted_at=deleted_at
        )
        deleted_parent = Parent(user=deleted_parent_user, phone="555-1999", deleted_at=deleted_at)
        course = Course(
            name="Math",
            code="STATS-MATH",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
            school_class=school_class,
        )
        old_course = Course(
            name="History",
            code="STATS-HIST",
            teacher=self.teacher,
            term="3ème Trimestre",
            school_year="2025-2026",
        )
        self.db.add_all(
            [school_class, deleted_class, student, deleted_student, deleted_teacher, deleted_parent, course, old_course]
        )
        self.db.flush()

        term2_item = GradeItem(course=course, title="Quiz", category="Quiz", max_score=20, weight=1, term="2ème Trimestre")
        term3_deleted_item = GradeItem(
            course=course,
            title="Deleted Exam",
            category="Exam",
            max_score=20,
            weight=1,
            term="3ème Trimestre",
            deleted_at=deleted_at,
        )
        self.db.add_all([term2_item, term3_deleted_item])
        self.db.flush()
        self.db.add_all(
            [
                Grade(student=student, grade_item=term2_item, score=17, submitted_by_teacher=self.teacher),
                CourseResult(student=student, course=old_course, term="3ème Trimestre", average=18, letter_grade="A"),
                ReportCard(
                    student=student,
                    term="1er Trimestre",
                    school_year="2026-2027",
                    overall_average=14,
                    status="approved",
                ),
                ReportCard(
                    student=student,
                    term="2ème Trimestre",
                    school_year="2026-2027",
                    overall_average=15,
                    status="draft",
                ),
                ReportCard(
                    student=student,
                    term="2ème Trimestre",
                    school_year="2026-2027",
                    overall_average=16,
                    status="sent",
                ),
                ReportCard(
                    student=deleted_student,
                    term="3ème Trimestre",
                    school_year="2026-2027",
                    overall_average=19,
                    status="sent",
                ),
            ]
        )
        self.db.commit()

        response = self.client.get("/api/v1/admin/stats", headers=self._admin())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["students"], 1)
        self.assertEqual(data["teachers"], 1)
        self.assertEqual(data["parents"], 1)
        self.assertEqual(data["classes"], 1)
        self.assertEqual(data["current_term"], {"name": "2ème Trimestre", "trimester": 2})
        self.assertEqual(data["bulletins"], {"generated": 2, "approved": 0, "sent": 1})

    def test_no_active_school_year_returns_null_current_term(self):
        response = self.client.get("/api/v1/admin/stats", headers=self._admin())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIsNone(data["current_term"])
        self.assertEqual(data["bulletins"], {"generated": 0, "approved": 0, "sent": 0})

    def test_school_year_without_activity_falls_back_to_first_trimester(self):
        self.db.add(
            Class(name_fr="6ème", name_en="JSS1", school_level="college", sort_order=1, school_year="2026-2027")
        )
        self.db.commit()

        response = self.client.get("/api/v1/admin/stats", headers=self._admin())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["current_term"], {"name": "1er Trimestre", "trimester": 1})
        self.assertEqual(data["bulletins"], {"generated": 0, "approved": 0, "sent": 0})


if __name__ == "__main__":
    unittest.main()
