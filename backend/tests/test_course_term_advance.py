import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Course, CourseResult, Enrollment, GradeItem, Student, Teacher, User

YEAR = "2026-2027"
OTHER_YEAR = "2027-2028"
TERM1 = "1er Trimestre"
TERM2 = "2ème Trimestre"


class TermAdvanceTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-advance@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-advance@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-ADV-1")
        self.db.add(self.teacher)

        self.terminale = Class(name_fr="Terminale C", school_level="college", sort_order=8, school_year=YEAR)
        self.db.add(self.terminale)
        self.db.flush()

        # Beninese course (FRENCH + collège class) with a full closing term.
        self.course_math = Course(
            name="Mathématique",
            code="ADV-MATH",
            teacher_id=self.teacher.id,
            term=TERM1,
            school_year=YEAR,
            language_group="FRENCH",
            class_id=self.terminale.id,
        )
        # Beninese course missing its Devoir and Composition for the closing term.
        self.course_philo = Course(
            name="Philosophie",
            code="ADV-PHIL",
            teacher_id=self.teacher.id,
            term=TERM1,
            school_year=YEAR,
            language_group="FRENCH",
            class_id=self.terminale.id,
        )
        # Weighted course (no Beninese warnings apply).
        self.course_english = Course(
            name="English studies",
            code="ADV-ENG",
            teacher_id=self.teacher.id,
            term=TERM1,
            school_year=YEAR,
            language_group="ENGLISH",
            class_id=self.terminale.id,
        )
        # A course in a different year must never be touched.
        self.course_other_year = Course(
            name="Mathématique",
            code="ADV-MATH-NEXT",
            teacher_id=self.teacher.id,
            term=TERM1,
            school_year=OTHER_YEAR,
            language_group="FRENCH",
            class_id=None,
        )
        # A soft-deleted course in the target year must never be touched.
        self.course_deleted = Course(
            name="Ancienne matière",
            code="ADV-DEL",
            teacher_id=self.teacher.id,
            term=TERM1,
            school_year=YEAR,
            language_group=None,
            class_id=None,
            deleted_at=func.now(),
        )
        self.db.add_all(
            [self.course_math, self.course_philo, self.course_english, self.course_other_year, self.course_deleted]
        )

        self.student = Student(first_name="Ayo", last_name="Akowanou", student_number="STU-ADV-1", class_id=None)
        self.db.add(self.student)
        self.db.flush()
        self.db.add(Enrollment(student_id=self.student.id, course_id=self.course_math.id))

        # Full Beninese item set for the math course's closing term.
        for title, item_type in (("Interro 1", "INTERRO"), ("Devoir", "DEVOIR"), ("Composition", "COMPOSITION")):
            self.db.add(
                GradeItem(
                    course_id=self.course_math.id,
                    title=title,
                    category=None,
                    max_score=20,
                    weight=None,
                    item_type=item_type,
                    term=TERM1,
                )
            )
        # Calculated result for the math course's current term.
        self.db.add(
            CourseResult(
                student_id=self.student.id,
                course_id=self.course_math.id,
                term=TERM1,
                average=14.5,
                letter_grade="B",
                scale="20",
                calculated_at=func.now(),
            )
        )
        self.db.commit()

    def _login(self, email) -> dict:
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self) -> dict:
        return self._login("admin-advance@example.test")

    def test_advance_updates_only_target_year(self):
        response = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["updated_count"], 3)
        self.assertEqual(body["skipped_count"], 0)

        terms = dict(self.db.execute(select(Course.code, Course.term)).all())
        self.assertEqual(terms["ADV-MATH"], TERM2)
        self.assertEqual(terms["ADV-PHIL"], TERM2)
        self.assertEqual(terms["ADV-ENG"], TERM2)
        self.assertEqual(terms["ADV-MATH-NEXT"], TERM1)
        self.assertEqual(terms["ADV-DEL"], TERM1)

    def test_advance_is_idempotent(self):
        headers = self._admin()
        first = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        self.assertEqual(first.json()["updated_count"], 3)
        second = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["updated_count"], 0)
        self.assertEqual(second.json()["skipped_count"], 3)

    def test_backward_move_allowed(self):
        headers = self._admin()
        self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        back = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM1},
            headers=headers,
        )
        self.assertEqual(back.status_code, 200)
        self.assertEqual(back.json()["updated_count"], 3)

    def test_requires_admin(self):
        headers = self._login("teacher-advance@example.test")
        response = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)
        preview = self.client.get(
            "/api/v1/courses/advance-term/preview",
            params={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        self.assertEqual(preview.status_code, 403)

    def test_free_text_term_rejected(self):
        response = self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": "Fall"},
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 422)

    def test_audit_entry_written(self):
        self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=self._admin(),
        )
        log = self.db.scalar(select(AuditLog).where(AuditLog.action == "courses_term_advanced"))
        self.assertIsNotNone(log)
        self.assertEqual(log.new_value["target_term"], TERM2)
        self.assertEqual(log.new_value["updated_count"], 3)
        self.assertEqual(sorted(log.new_value["updated_codes"]), ["ADV-ENG", "ADV-MATH", "ADV-PHIL"])

    def test_no_audit_entry_when_nothing_updated(self):
        headers = self._admin()
        self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        count = self.db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.action == "courses_term_advanced")
        )
        self.assertEqual(count, 1)

    def test_preview_counts_and_warnings(self):
        response = self.client.get(
            "/api/v1/courses/advance-term/preview",
            params={"school_year": YEAR, "target_term": TERM2},
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_count"], 3)
        self.assertEqual(body["already_on_target_count"], 0)
        by_code = {row["code"]: row for row in body["courses"]}

        math = by_code["ADV-MATH"]
        self.assertEqual(math["current_term"], TERM1)
        self.assertEqual(math["enrolled_count"], 1)
        self.assertEqual(math["results_calculated_count"], 1)
        self.assertEqual(math["warnings"], [])

        philo = by_code["ADV-PHIL"]
        self.assertEqual(philo["enrolled_count"], 0)
        self.assertEqual(philo["results_calculated_count"], 0)
        self.assertEqual(
            sorted(philo["warnings"]),
            ["missing_composition", "missing_devoir", "missing_interro"],
        )

        english = by_code["ADV-ENG"]
        self.assertEqual(english["warnings"], [])

        # Deleted and other-year courses are absent from the preview.
        self.assertNotIn("ADV-DEL", by_code)
        self.assertNotIn("ADV-MATH-NEXT", by_code)

    def test_preview_marks_courses_already_on_target(self):
        headers = self._admin()
        self.client.post(
            "/api/v1/courses/advance-term",
            json={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        response = self.client.get(
            "/api/v1/courses/advance-term/preview",
            params={"school_year": YEAR, "target_term": TERM2},
            headers=headers,
        )
        body = response.json()
        self.assertEqual(body["already_on_target_count"], 3)
        self.assertTrue(all(row["already_on_target"] for row in body["courses"]))


if __name__ == "__main__":
    unittest.main()
