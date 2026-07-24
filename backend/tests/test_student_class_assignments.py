import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Class,
    Course,
    Enrollment,
    Parent,
    Student,
    StudentClassAssignment,
    Teacher,
    User,
)
from services.student_assignments import set_student_assignment


YEAR_A = "2026-2027"
YEAR_B = "2027-2028"


class StudentClassAssignmentReproTests(unittest.TestCase):
    password = "test-password-123"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

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
            name="ZZ-TEST Assignment Admin",
            email="zz-test-assignment-admin@example.test",
            password_hash=hash_password(self.password),
            role="admin",
        )
        teacher_user = User(
            name="ZZ-TEST Assignment Teacher",
            email="zz-test-assignment-teacher@example.test",
            password_hash=hash_password(self.password),
            role="teacher",
        )
        parent_user = User(
            name="ZZ-TEST Assignment Parent",
            email="zz-test-assignment-parent@example.test",
            password_hash=hash_password(self.password),
            role="parent",
        )
        self.db.add_all([self.admin, teacher_user, parent_user])
        self.db.flush()
        self.teacher = Teacher(user=teacher_user, employee_number="ZZ-TEST-ASSIGN-TCH")
        self.parent = Parent(user=parent_user, phone="+2290100000000")
        self.class_a = Class(
            name_fr="6eme A",
            school_level="college",
            sort_order=7,
            school_year=YEAR_A,
        )
        self.db.add_all([self.teacher, self.parent, self.class_a])
        self.db.flush()
        self.student = Student(
            first_name="ZZ-TEST",
            last_name="Assignment Student",
            student_number="ZZ-TEST-ASSIGN-STU",
            school_class=self.class_a,
        )
        self.db.add(self.student)
        self.db.flush()
        self.db.add(
            StudentClassAssignment(
                student=self.student,
                school_year=YEAR_A,
                class_id=self.class_a.id,
                class_name_snapshot=self.class_a.name_fr,
            )
        )
        self.course_a = Course(
            name="ZZ-TEST Mathematics A",
            code="ZZ-TEST-ASSIGN-MATH-A",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year=YEAR_A,
            school_class=self.class_a,
        )
        self.db.add(self.course_a)
        self.db.flush()
        self.db.add(Enrollment(student=self.student, course=self.course_a))
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

    def _create_year_b_class(self) -> Class:
        school_class = Class(
            name_fr="5eme B",
            school_level="college",
            sort_order=8,
            school_year=YEAR_B,
        )
        self.db.add(school_class)
        self.db.commit()
        self.db.refresh(school_class)
        return school_class

    def test_new_year_classes_do_not_change_permanent_people_lists(self):
        headers = self._headers()
        before = {
            "students": self.client.get(
                "/api/v1/students", params={"school_year": YEAR_A}, headers=headers
            ).json(),
            "teachers": self.client.get("/api/v1/teachers", headers=headers).json(),
            "parents": self.client.get("/api/v1/parents", headers=headers).json(),
        }

        self._create_year_b_class()

        after = {
            "students": self.client.get(
                "/api/v1/students", params={"school_year": YEAR_B}, headers=headers
            ).json(),
            "teachers": self.client.get("/api/v1/teachers", headers=headers).json(),
            "parents": self.client.get("/api/v1/parents", headers=headers).json(),
        }
        self.assertEqual(
            {row["id"] for row in before["students"]},
            {row["id"] for row in after["students"]},
        )
        self.assertEqual(before["teachers"], after["teachers"])
        self.assertEqual(before["parents"], after["parents"])

    def test_assignment_resolves_independently_for_each_school_year(self):
        class_b = self._create_year_b_class()
        self.student.class_id = class_b.id
        set_student_assignment(self.db, self.student, class_b)
        self.db.commit()
        headers = self._headers()

        year_a = self.client.get(
            "/api/v1/students", params={"school_year": YEAR_A}, headers=headers
        )
        year_b = self.client.get(
            "/api/v1/students", params={"school_year": YEAR_B}, headers=headers
        )

        self.assertEqual(year_a.status_code, 200, year_a.text)
        self.assertEqual(year_b.status_code, 200, year_b.text)
        self.assertEqual(year_a.json()[0]["class_id"], str(self.class_a.id))
        self.assertEqual(year_a.json()[0]["class_name"], "6eme A")
        self.assertEqual(year_b.json()[0]["class_id"], str(class_b.id))
        self.assertEqual(year_b.json()[0]["class_name"], "5eme B")

    def test_class_filter_uses_selected_year_assignment(self):
        class_b = self._create_year_b_class()
        self.student.class_id = class_b.id
        set_student_assignment(self.db, self.student, class_b)
        self.db.commit()

        response = self.client.get(
            "/api/v1/students",
            params={"school_year": YEAR_A, "class_id": str(self.class_a.id)},
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["id"] for row in response.json()], [str(self.student.id)])

    def test_unassigned_filter_returns_student_with_explicit_state(self):
        self._create_year_b_class()

        response = self.client.get(
            "/api/v1/students",
            params={"school_year": YEAR_B, "unassigned": "true"},
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)
        row = response.json()[0]
        self.assertEqual(row["id"], str(self.student.id))
        self.assertIsNone(row["class_id"])
        self.assertIsNone(row["class_name"])
        self.assertEqual(row["assignment_school_year"], YEAR_B)
        self.assertTrue(row["is_unassigned_for_year"])

    def test_create_and_edit_student_sync_year_assignments(self):
        class_b = self._create_year_b_class()
        headers = self._headers()
        created = self.client.post(
            "/api/v1/students",
            json={
                "first_name": "ZZ-TEST",
                "last_name": "Created Assignment",
                "student_number": "ZZ-TEST-ASSIGN-CREATED",
                "class_id": str(self.class_a.id),
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        student_id = UUID(created.json()["id"])
        assignment_a = self.db.query(StudentClassAssignment).filter_by(
            student_id=student_id, school_year=YEAR_A
        ).one()
        self.assertEqual(assignment_a.class_id, self.class_a.id)

        updated = self.client.put(
            f"/api/v1/students/{student_id}",
            json={"class_id": str(class_b.id), "class_school_year": YEAR_B},
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        assignment_b = self.db.query(StudentClassAssignment).filter_by(
            student_id=student_id, school_year=YEAR_B
        ).one()
        self.assertEqual(assignment_b.class_id, class_b.id)
        self.assertEqual(assignment_a.class_id, self.class_a.id)

        cleared = self.client.put(
            f"/api/v1/students/{student_id}",
            json={"class_id": None, "class_school_year": YEAR_B},
            headers=headers,
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(
            self.db.query(StudentClassAssignment).filter_by(
                student_id=student_id, school_year=YEAR_B
            ).one_or_none()
        )


if __name__ == "__main__":
    unittest.main()
