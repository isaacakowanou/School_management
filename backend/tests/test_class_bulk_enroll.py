"""A1.11 — bulk-enroll a class's students into the class's courses."""
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Course, Enrollment, Student, Teacher, User

SCHOOL_YEAR = "2026-2027"
OTHER_YEAR = "2027-2028"


class BulkEnrollClassStudentsTests(unittest.TestCase):
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
        u = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(u)
        return u

    def _seed(self):
        self.admin_user = self._user(name="Admin", email="admin-enr@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-enr@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-ENR-1")
        self.db.add(self.teacher)

        self.sixieme = Class(
            name_fr="6ème", school_level="college", sort_order=1, school_year=SCHOOL_YEAR
        )
        # An empty class for the "no students / no courses" cases.
        self.cinquieme = Class(
            name_fr="5ème", school_level="college", sort_order=2, school_year=SCHOOL_YEAR
        )
        self.db.add_all([self.sixieme, self.cinquieme])
        self.db.flush()

        # 3 students in 6ème + 1 unassigned that must NOT be swept in.
        self.students = [
            Student(first_name=f"S{i}", last_name="X", grade_level="6ème",
                    student_number=f"S6-{i}", class_id=self.sixieme.id)
            for i in range(3)
        ]
        self.unassigned = Student(
            first_name="Solo", last_name="X", grade_level="6ème", student_number="S6-NC",
        )
        self.db.add_all(self.students + [self.unassigned])

        # 2 courses tagged with 6ème for this year.
        self.courses = [
            Course(name=n, code=c, teacher_id=self.teacher.id, grade_level="6ème",
                   term="1er Trimestre", school_year=SCHOOL_YEAR, class_id=self.sixieme.id)
            for n, c in [("Maths", "M6"), ("Anglais", "A6")]
        ]
        # A course tagged with 6ème but for a DIFFERENT school year — must be
        # ignored (the class row's year drives the filter, not the tag).
        self.wrong_year_course = Course(
            name="Maths", code="M6-NEXT", teacher_id=self.teacher.id, grade_level="6ème",
            term="1er Trimestre", school_year=OTHER_YEAR, class_id=self.sixieme.id,
        )
        # A course with no class_id — untagged courses are not implicitly swept.
        self.untagged_course = Course(
            name="Info", code="INFO", teacher_id=self.teacher.id, grade_level="6ème",
            term="1er Trimestre", school_year=SCHOOL_YEAR,
        )
        self.db.add_all(self.courses + [self.wrong_year_course, self.untagged_course])
        self.db.commit()

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin_user.email)

    def _post(self, class_id=None, headers=None):
        return self.client.post(
            f"/api/v1/classes/{class_id or self.sixieme.id}/bulk-enroll",
            headers=headers or self._admin(),
        )

    def _preview(self, class_id=None, headers=None):
        return self.client.get(
            f"/api/v1/classes/{class_id or self.sixieme.id}/enrollment-preview",
            headers=headers or self._admin(),
        )

    # --- happy path ---

    def test_creates_all_missing_enrollments(self):
        r = self._post()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["students_in_class"], 3)
        self.assertEqual(body["courses_in_class"], 2)
        self.assertEqual(body["enrollments_created"], 6)
        self.assertEqual(body["enrollments_skipped"], 0)
        self.assertEqual(body["school_year"], SCHOOL_YEAR)

        # Every (student, course) pair now exists, and only for the two tagged
        # in-year courses — wrong-year + untagged courses got nothing.
        rows = self.db.scalars(select(Enrollment)).all()
        self.assertEqual(len(rows), 6)
        for course in (self.wrong_year_course, self.untagged_course):
            enrolled_for = [e for e in rows if e.course_id == course.id]
            self.assertEqual(enrolled_for, [])
        # The unassigned student wasn't enrolled anywhere.
        self.assertEqual(
            [e for e in rows if e.student_id == self.unassigned.id],
            [],
        )

    def test_idempotent_rerun(self):
        self._post()
        r = self._post()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["enrollments_created"], 0)
        self.assertEqual(body["enrollments_skipped"], 6)
        self.assertEqual(len(self.db.scalars(select(Enrollment)).all()), 6)

    def test_partial_state_only_fills_gaps(self):
        # Pre-enroll one student in one course; the action fills the rest.
        self.db.add(Enrollment(student_id=self.students[0].id, course_id=self.courses[0].id))
        self.db.commit()

        r = self._post()
        body = r.json()
        self.assertEqual(body["enrollments_created"], 5)
        self.assertEqual(body["enrollments_skipped"], 1)
        self.assertEqual(len(self.db.scalars(select(Enrollment)).all()), 6)

    # --- guards ---

    def test_empty_class_returns_ok_empty_status_no_writes(self):
        r = self._post(class_id=self.cinquieme.id)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["students_in_class"], 0)
        self.assertEqual(body["courses_in_class"], 0)
        self.assertEqual(body["enrollments_created"], 0)
        self.assertEqual(self.db.scalars(select(Enrollment)).all(), [])

    def test_class_with_students_but_no_courses_returns_empty(self):
        # Give 5ème students but no courses.
        self.db.add(
            Student(first_name="Solo", last_name="Y", grade_level="5ème",
                    student_number="S5-1", class_id=self.cinquieme.id)
        )
        self.db.commit()
        body = self._post(class_id=self.cinquieme.id).json()
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["students_in_class"], 1)
        self.assertEqual(body["courses_in_class"], 0)

    def test_missing_class_is_404(self):
        r = self.client.post(
            "/api/v1/classes/00000000-0000-0000-0000-000000000000/bulk-enroll",
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 404)

    def test_requires_admin(self):
        r = self._post(headers=self._headers(self.teacher_user.email))
        self.assertEqual(r.status_code, 403)

    # --- audit ---

    def test_writes_single_batch_audit_entry(self):
        self._post()
        logs = self.db.scalars(
            select(AuditLog).where(AuditLog.action == "class_students_bulk_enrolled")
        ).all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_user_id, self.admin_user.id)
        self.assertEqual(logs[0].new_value["class_id"], str(self.sixieme.id))
        self.assertEqual(logs[0].new_value["school_year"], SCHOOL_YEAR)
        self.assertEqual(logs[0].new_value["enrollments_created"], 6)
        self.assertEqual(logs[0].new_value["enrollments_skipped"], 0)

    def test_noop_rerun_writes_no_audit_entry(self):
        self._post()
        self._post()
        logs = self.db.scalars(
            select(AuditLog).where(AuditLog.action == "class_students_bulk_enrolled")
        ).all()
        self.assertEqual(len(logs), 1)

    def test_empty_class_writes_no_audit_entry(self):
        self._post(class_id=self.cinquieme.id)
        self.assertEqual(
            self.db.scalars(
                select(AuditLog).where(AuditLog.action == "class_students_bulk_enrolled")
            ).all(),
            [],
        )

    # --- preview ---

    def test_preview_mirrors_post_counts(self):
        body = self._preview().json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["students_in_class"], 3)
        self.assertEqual(body["courses_in_class"], 2)
        self.assertEqual(body["enrollments_to_create"], 6)
        self.assertEqual(body["enrollments_already_existing"], 0)
        # No writes.
        self.assertEqual(self.db.scalars(select(Enrollment)).all(), [])

    def test_preview_reflects_partial_state(self):
        self.db.add(Enrollment(student_id=self.students[0].id, course_id=self.courses[0].id))
        self.db.commit()
        body = self._preview().json()
        self.assertEqual(body["enrollments_to_create"], 5)
        self.assertEqual(body["enrollments_already_existing"], 1)

    def test_preview_empty_class(self):
        body = self._preview(class_id=self.cinquieme.id).json()
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["enrollments_to_create"], 0)

    def test_preview_requires_admin(self):
        r = self._preview(headers=self._headers(self.teacher_user.email))
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
