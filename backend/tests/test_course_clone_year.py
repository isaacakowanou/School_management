import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, Enrollment, GradeItem, Student, Subject, Teacher, User

SOURCE_YEAR = "2026-2027"
TARGET_YEAR = "2027-2028"


class CloneYearTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-clone@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-clone@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-CLONE-1")
        self.db.add(self.teacher)

        # Source-year classes 6ème and 5ème; only 6ème exists in the target year.
        self.source_sixieme = Class(
            name_fr="6ème", school_level="college", sort_order=1, school_year=SOURCE_YEAR
        )
        self.source_cinquieme = Class(
            name_fr="5ème", school_level="college", sort_order=2, school_year=SOURCE_YEAR
        )
        self.target_sixieme = Class(
            name_fr="6ème", school_level="college", sort_order=1, school_year=TARGET_YEAR
        )
        self.db.add_all([self.source_sixieme, self.source_cinquieme, self.target_sixieme])

        self.subject = Subject(
            name_fr="Mathématique",
            name_en="Mathematics",
            section="FRENCH",
            level_group="COLLEGE_FIRST_CYCLE",
            sort_order=6,
        )
        self.db.add(self.subject)
        self.db.flush()

        self.course_math = Course(
            name="Mathématique",
            code="MATH6",
            teacher_id=self.teacher.id,
            term="1er Trimestre",
            school_year=SOURCE_YEAR,
            language_group="FRENCH",
            class_id=self.source_sixieme.id,
            subject_id=self.subject.id,
        )
        self.course_english = Course(
            name="English studies",
            code="ENG5",
            teacher_id=self.teacher.id,
            term="1er Trimestre",
            school_year=SOURCE_YEAR,
            language_group="ENGLISH",
            class_id=self.source_cinquieme.id,
        )
        self.course_no_class = Course(
            name="Informatique",
            code="INFO",
            teacher_id=self.teacher.id,
            term="1er Trimestre",
            school_year=SOURCE_YEAR,
        )
        self.db.add_all([self.course_math, self.course_english, self.course_no_class])
        self.db.flush()

        # Grade item + enrollment on the source course: clones must get neither.
        self.student = Student(
            first_name="Ama", last_name="Kow", student_number="S-CLONE-1"
        )
        self.db.add(self.student)
        self.db.flush()
        self.db.add(
            GradeItem(
                course_id=self.course_math.id,
                title="Devoir 1",
                category="test",
                max_score=20,
                weight=1.0,
                term="1er Trimestre",
            )
        )
        self.db.add(Enrollment(student_id=self.student.id, course_id=self.course_math.id))
        self.db.commit()

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin_user.email)

    def _clone(self, source_year=SOURCE_YEAR, target_year=TARGET_YEAR, headers=None):
        return self.client.post(
            "/api/v1/courses/clone-year",
            json={"source_year": source_year, "target_year": target_year},
            headers=headers or self._admin(),
        )

    def test_clone_creates_courses_with_remapped_classes(self):
        r = self._clone()
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["created_count"], 3)
        self.assertEqual(body["unmatched_class_names"], ["5ème"])

        clones = {
            c.code: c
            for c in self.db.scalars(select(Course).where(Course.school_year == TARGET_YEAR)).all()
        }
        self.assertEqual(len(clones), 3)

        math = clones[f"MATH6-{TARGET_YEAR}"]
        self.assertEqual(math.name, "Mathématique")
        self.assertEqual(math.language_group, "FRENCH")
        self.assertEqual(math.teacher_id, self.teacher.id)
        self.assertEqual(math.subject_id, self.subject.id)
        # 6ème exists in the target year: remapped, not carried over.
        self.assertEqual(math.class_id, self.target_sixieme.id)

        english = clones[f"ENG5-{TARGET_YEAR}"]
        # 5ème has no target-year class: link is dropped, reported above.
        self.assertIsNone(english.class_id)
        self.assertEqual(english.language_group, "ENGLISH")

        self.assertIsNone(clones[f"INFO-{TARGET_YEAR}"].class_id)

    def test_clone_copies_no_grade_items_or_enrollments(self):
        self._clone()
        clone_ids = list(
            self.db.scalars(select(Course.id).where(Course.school_year == TARGET_YEAR)).all()
        )
        self.assertEqual(len(clone_ids), 3)
        grade_items = self.db.scalars(
            select(GradeItem).where(GradeItem.course_id.in_(clone_ids))
        ).all()
        enrollments = self.db.scalars(
            select(Enrollment).where(Enrollment.course_id.in_(clone_ids))
        ).all()
        self.assertEqual(grade_items, [])
        self.assertEqual(enrollments, [])
        # Source course keeps its own.
        self.assertEqual(
            len(self.db.scalars(select(GradeItem).where(GradeItem.course_id == self.course_math.id)).all()),
            1,
        )

    def test_clone_always_starts_courses_in_first_trimester(self):
        self.course_math.term = "3\u00e8me Trimestre"
        self.db.commit()

        response = self._clone()

        self.assertEqual(response.status_code, 201, response.text)
        clone = self.db.scalar(
            select(Course).where(Course.code == f"MATH6-{TARGET_YEAR}")
        )
        self.assertEqual(clone.term, "1er Trimestre")

    def test_clone_preserves_all_course_configuration_fields(self):
        self.assertIn("grading_system", Course.__table__.columns)
        self.course_math.term = "3\u00e8me Trimestre"
        self.course_math.grading_system = "BENINESE"
        self.course_math.coefficient = 4
        self.db.commit()

        response = self._clone()

        self.assertEqual(response.status_code, 201, response.text)
        clone = self.db.scalar(
            select(Course).where(Course.code == f"MATH6-{TARGET_YEAR}")
        )
        self.assertEqual(clone.name, self.course_math.name)
        self.assertEqual(clone.teacher_id, self.course_math.teacher_id)
        self.assertEqual(clone.language_group, self.course_math.language_group)
        self.assertEqual(clone.subject_id, self.course_math.subject_id)
        self.assertEqual(clone.coefficient, self.course_math.coefficient)
        self.assertEqual(clone.grading_system, self.course_math.grading_system)
        self.assertEqual(clone.class_id, self.target_sixieme.id)
        self.assertEqual(clone.school_year, TARGET_YEAR)
        self.assertEqual(clone.term, "1er Trimestre")
        self.assertEqual(clone.code, f"{self.course_math.code}-{TARGET_YEAR}")

    def test_every_course_column_is_classified_by_clone_contract(self):
        copied = {
            "name",
            "teacher_id",
            "language_group",
            "subject_id",
            "coefficient",
            "grading_system",
        }
        transformed = {"code", "term", "school_year", "class_id"}
        intentionally_excluded = {
            "id",
            "deleted_at",
            "deleted_batch_id",
            "created_at",
            "updated_at",
        }

        self.assertEqual(
            set(Course.__table__.columns.keys()),
            copied | transformed | intentionally_excluded,
        )

    def test_clone_skips_existing_target_clones_and_creates_missing_courses(self):
        self.db.add(
            Course(
                name="Existing Math Clone",
                code=f"MATH6-{TARGET_YEAR}",
                teacher_id=self.teacher.id,
                term="1er Trimestre",
                school_year=TARGET_YEAR,
            )
        )
        self.db.commit()

        r = self._clone()

        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["created_count"], 2)
        self.assertEqual(r.json()["skipped_count"], 1)
        clones = self.db.scalars(select(Course).where(Course.school_year == TARGET_YEAR)).all()
        self.assertEqual(len(clones), 3)

    def test_clone_all_existing_target_clones_is_idempotent_noop(self):
        first = self._clone()
        self.assertEqual(first.status_code, 201, first.text)

        second = self._clone()

        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["created_count"], 0)
        self.assertEqual(second.json()["skipped_count"], 3)
        self.assertTrue(second.json()["nothing_to_do"])
        clones = self.db.scalars(select(Course).where(Course.school_year == TARGET_YEAR)).all()
        self.assertEqual(len(clones), 3)

    def test_clone_refuses_same_year(self):
        r = self._clone(target_year=SOURCE_YEAR)
        self.assertEqual(r.status_code, 422)

    def test_clone_refuses_empty_source_year(self):
        r = self._clone(source_year="1999-2000")
        self.assertEqual(r.status_code, 422)

    def test_clone_refuses_code_collision(self):
        # A course in a third year already holds one of the would-be clone codes.
        self.db.add(
            Course(
                name="Squatter",
                code=f"MATH6-{TARGET_YEAR}",
                teacher_id=self.teacher.id,
                term="1er Trimestre",
                school_year="2028-2029",
            )
        )
        self.db.commit()
        r = self._clone()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["codes"], [f"MATH6-{TARGET_YEAR}"])
        # Nothing was created.
        self.assertEqual(
            self.db.scalars(select(Course).where(Course.school_year == TARGET_YEAR)).all(), []
        )

    def test_clone_requires_admin(self):
        r = self._clone(headers=self._headers(self.teacher_user.email))
        self.assertEqual(r.status_code, 403)

    def test_course_list_filters_by_school_year(self):
        r = self.client.get(f"/api/v1/courses?school_year={SOURCE_YEAR}", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 3)
        r = self.client.get(f"/api/v1/courses?school_year={TARGET_YEAR}", headers=self._admin())
        self.assertEqual(r.json(), [])


if __name__ == "__main__":
    unittest.main()
