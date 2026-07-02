import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Course, Enrollment, Student, Teacher, User


class EnrollmentRouteTests(unittest.TestCase):
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

    def _create_user(self, *, name: str, email: str, role: str) -> User:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(self.password),
            role=role,
        )
        self.db.add(user)
        return user

    def _seed(self) -> None:
        self.admin_user = self._create_user(
            name="Admin User",
            email="admin-enrollments@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-enrollments@example.test",
            role="teacher",
        )
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-enrollments@example.test",
            role="parent",
        )
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="TCH-ENROLL")
        self.student = Student(
            first_name="Ada",
            last_name="Lovelace",
            student_number="ENROLL-STU-001",
            grade_level="12",
        )
        self.duplicate_student = Student(
            first_name="Grace",
            last_name="Hopper",
            student_number="ENROLL-STU-002",
            grade_level="12",
        )
        self.db.add_all([self.teacher, self.student, self.duplicate_student])
        self.db.flush()
        self.course = Course(
            name="Enrollment Course",
            code="ENROLL-101",
            teacher=self.teacher,
            grade_level="12",
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()
        self.existing_enrollment = Enrollment(student=self.duplicate_student, course=self.course)
        self.db.add(self.existing_enrollment)
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _enrollment_payload(self, *, student_id=None, course_id=None) -> dict[str, str]:
        return {
            "student_id": str(student_id or self.student.id),
            "course_id": str(course_id or self.course.id),
        }

    def test_admin_can_enroll_student_in_course(self):
        response = self.client.post(
            "/api/v1/enrollments",
            json=self._enrollment_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["student_id"], str(self.student.id))
        self.assertEqual(data["course_id"], str(self.course.id))

        enrollment = self.db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == self.student.id,
                Enrollment.course_id == self.course.id,
            )
        )
        self.assertIsNotNone(enrollment)

    def test_non_admin_cannot_enroll_student_in_course(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/enrollments",
                    json=self._enrollment_payload(),
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_enrollment_is_rejected(self):
        response = self.client.post(
            "/api/v1/enrollments",
            json=self._enrollment_payload(student_id=self.duplicate_student.id),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Student is already enrolled")

    def test_missing_course_or_student_is_handled_cleanly(self):
        missing_student_response = self.client.post(
            "/api/v1/enrollments",
            json=self._enrollment_payload(student_id=uuid4()),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(missing_student_response.status_code, 404)
        self.assertEqual(missing_student_response.json()["detail"], "Student not found")

        missing_course_response = self.client.post(
            "/api/v1/enrollments",
            json=self._enrollment_payload(course_id=uuid4()),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(missing_course_response.status_code, 404)
        self.assertEqual(missing_course_response.json()["detail"], "Course not found")

    def test_create_enrollment_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/enrollments",
            json=self._enrollment_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        enrollment = self.db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == self.student.id,
                Enrollment.course_id == self.course.id,
            )
        )
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "student_enrolled_in_course",
                AuditLog.entity_type == "enrollment",
                AuditLog.entity_id == enrollment.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "student_id": str(self.student.id),
                "course_id": str(self.course.id),
            },
        )

    def test_admin_can_unenroll_student_from_course(self):
        response = self.client.delete(
            f"/api/v1/courses/{self.course.id}/students/{self.duplicate_student.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Student unenrolled from course")
        enrollment = self.db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == self.duplicate_student.id,
                Enrollment.course_id == self.course.id,
            )
        )
        self.assertIsNone(enrollment)

    def test_non_admin_cannot_unenroll_student_from_course(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.delete(
                    f"/api/v1/courses/{self.course.id}/students/{self.duplicate_student.id}",
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_missing_enrollment_unenroll_gets_404(self):
        response = self.client.delete(
            f"/api/v1/courses/{self.course.id}/students/{self.student.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Enrollment not found")

    def test_unenroll_student_from_course_writes_audit_log(self):
        enrollment_id = self.existing_enrollment.id

        response = self.client.delete(
            f"/api/v1/courses/{self.course.id}/students/{self.duplicate_student.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "student_unenrolled_from_course",
                AuditLog.entity_type == "enrollment",
                AuditLog.entity_id == enrollment_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(
            audit_log.old_value,
            {
                "student_id": str(self.duplicate_student.id),
                "course_id": str(self.course.id),
            },
        )
        self.assertIsNone(audit_log.new_value)


if __name__ == "__main__":
    unittest.main()
