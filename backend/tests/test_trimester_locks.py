import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    AuditLog,
    Base,
    Course,
    CourseResult,
    Enrollment,
    Grade,
    GradeItem,
    ReportCard,
    ReportCardCourse,
    Student,
    Teacher,
    User,
)


class TrimesterLockRouteTests(unittest.TestCase):
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

    def _user(self, name: str, email: str, role: str) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _seed(self) -> None:
        self.admin_user = self._user("Lock Admin", "lock-admin@example.test", "admin")
        self.teacher_user = self._user("Lock Teacher", "lock-teacher@example.test", "teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="LOCK-T-001")
        self.student = Student(
            first_name="ZZ-TEST-Lock",
            last_name="Student",
            student_number="ZZ-TEST-LOCK-001",
        )
        self.db.add_all([self.teacher, self.student])
        self.db.flush()
        self.course = Course(
            name="ZZ-TEST-Lock Mathematics",
            code="ZZ-TEST-LOCK-MATH",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
            grading_system="WEIGHTED",
        )
        self.db.add(self.course)
        self.db.flush()
        self.item_one = GradeItem(
            course=self.course,
            title="Homework",
            category="Homework",
            max_score=20,
            weight=0.5,
            term="1er Trimestre",
        )
        self.item_two = GradeItem(
            course=self.course,
            title="Exam",
            category="Exam",
            max_score=20,
            weight=0.5,
            term="1er Trimestre",
        )
        self.db.add_all([self.item_one, self.item_two])
        self.db.flush()
        self.grade_one = Grade(
            student=self.student,
            grade_item=self.item_one,
            score=15,
            submitted_by_teacher=self.teacher,
        )
        self.grade_two = Grade(
            student=self.student,
            grade_item=self.item_two,
            score=17,
            submitted_by_teacher=self.teacher,
        )
        self.db.add_all(
            [
                Enrollment(student=self.student, course=self.course),
                self.grade_one,
                self.grade_two,
            ]
        )
        self.db.flush()
        baseline = datetime.now(timezone.utc) - timedelta(days=1)
        self.result = CourseResult(
            student=self.student,
            course=self.course,
            term="1er Trimestre",
            average=16,
            letter_grade="B",
            scale="20",
            calculated_at=baseline,
        )
        self.report = ReportCard(
            student=self.student,
            term="1er Trimestre",
            school_year="2026-2027",
            overall_average=16,
            gpa=3,
            status="approved",
            approved_by_admin_id=self.admin_user.id,
            approved_at=baseline + timedelta(hours=1),
        )
        self.db.add_all([self.result, self.report])
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card=self.report,
                course=self.course,
                course_name=self.course.name,
                average=16,
                letter_grade="B",
            )
        )
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _set_lock(self, term: str, is_locked: bool = True):
        return self.client.put(
            "/api/v1/trimester-locks",
            headers=self._headers(self.admin_user.email),
            json={
                "school_year": self.course.school_year,
                "term": term,
                "is_locked": is_locked,
            },
        )

    def test_lock_state_is_independent_and_unlock_restores_teacher_writes(self):
        locked = self._set_lock("1er Trimestre")
        self.assertEqual(locked.status_code, 200, locked.text)

        states = self.client.get(
            "/api/v1/trimester-locks?school_year=2026-2027",
            headers=self._headers(self.teacher_user.email),
        )
        self.assertEqual(states.status_code, 200, states.text)
        by_term = {row["term"]: row["is_locked"] for row in states.json()}
        self.assertTrue(by_term["1er Trimestre"])
        self.assertFalse(by_term["2ème Trimestre"])
        self.assertFalse(by_term["3ème Trimestre"])

        blocked = self.client.post(
            "/api/v1/grade-items",
            headers=self._headers(self.teacher_user.email),
            json={
                "course_id": str(self.course.id),
                "title": "Blocked Quiz",
                "category": "Quiz",
                "max_score": 20,
                "weight": 0.1,
                "term": "1er Trimestre",
            },
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "trimester_locked")
        self.assertEqual(blocked.headers["x-error-code"], "trimester_locked")

        blocked_update = self.client.put(
            f"/api/v1/grade-items/{self.item_one.id}",
            headers=self._headers(self.teacher_user.email),
            json={"title": "Still Blocked"},
        )
        self.assertEqual(blocked_update.status_code, 403, blocked_update.text)
        self.assertEqual(blocked_update.json()["detail"]["code"], "trimester_locked")

        unlocked = self._set_lock("1er Trimestre", False)
        self.assertEqual(unlocked.status_code, 200, unlocked.text)
        allowed = self.client.put(
            f"/api/v1/grade-items/{self.item_one.id}",
            headers=self._headers(self.teacher_user.email),
            json={"title": "Homework Unlocked"},
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_grade_item_cannot_be_moved_into_a_locked_trimester(self):
        self.assertEqual(self._set_lock("2ème Trimestre").status_code, 200)
        response = self.client.put(
            f"/api/v1/grade-items/{self.item_one.id}",
            headers=self._headers(self.teacher_user.email),
            json={"term": "2ème Trimestre"},
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "trimester_locked")

    def test_teacher_grade_write_is_blocked_but_admin_override_is_audited(self):
        self.assertEqual(self._set_lock("1er Trimestre").status_code, 200)

        teacher_response = self.client.put(
            f"/api/v1/grades/{self.grade_one.id}",
            headers=self._headers(self.teacher_user.email),
            json={"score": 18},
        )
        self.assertEqual(teacher_response.status_code, 403, teacher_response.text)
        self.assertEqual(teacher_response.json()["detail"]["code"], "trimester_locked")

        admin_response = self.client.post(
            f"/api/v1/courses/{self.course.id}/grades/batch",
            headers=self._headers(self.admin_user.email),
            json={
                "entries": [
                    {
                        "student_id": str(self.student.id),
                        "grade_item_id": str(self.item_one.id),
                        "score": 18,
                    }
                ]
            },
        )
        self.assertEqual(admin_response.status_code, 200, admin_response.text)
        override = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "locked_trimester_override",
                AuditLog.entity_type == "grade",
                AuditLog.entity_id == self.grade_one.id,
            )
        )
        self.assertIsNotNone(override)
        self.assertEqual(override.actor_user_id, self.admin_user.id)
        self.assertEqual(override.new_value["operation"], "grade_updated")
        self.assertEqual(override.new_value["term"], "1er Trimestre")

    def test_teacher_batch_write_is_blocked_and_admin_item_override_is_audited(self):
        self.assertEqual(self._set_lock("1er Trimestre").status_code, 200)
        blocked = self.client.post(
            f"/api/v1/courses/{self.course.id}/grades/batch",
            headers=self._headers(self.teacher_user.email),
            json={
                "entries": [
                    {
                        "student_id": str(self.student.id),
                        "grade_item_id": str(self.item_one.id),
                        "score": 18,
                    }
                ]
            },
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "trimester_locked")

        created = self.client.post(
            "/api/v1/grade-items",
            headers=self._headers(self.admin_user.email),
            json={
                "course_id": str(self.course.id),
                "title": "Admin Override Quiz",
                "category": "Quiz",
                "max_score": 20,
                "weight": 0.1,
                "term": "1er Trimestre",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        item_id = created.json()["id"]
        override = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "locked_trimester_override",
                AuditLog.entity_type == "grade_item",
                AuditLog.entity_id == UUID(item_id),
            )
        )
        self.assertIsNotNone(override)
        self.assertEqual(override.new_value["operation"], "grade_item_created")

    def test_locked_admin_grade_override_uses_existing_report_staleness_flow(self):
        self.assertEqual(self._set_lock("1er Trimestre").status_code, 200)
        update = self.client.post(
            f"/api/v1/courses/{self.course.id}/grades/batch",
            headers=self._headers(self.admin_user.email),
            json={
                "entries": [
                    {
                        "student_id": str(self.student.id),
                        "grade_item_id": str(self.item_one.id),
                        "score": 19,
                    }
                ]
            },
        )
        self.assertEqual(update.status_code, 200, update.text)

        recalculate = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students?term=1er%20Trimestre",
            headers=self._headers(self.admin_user.email),
            json={"student_ids": [str(self.student.id)]},
        )
        self.assertEqual(recalculate.status_code, 200, recalculate.text)
        reports = self.client.get(
            "/api/v1/reports",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(reports.status_code, 200, reports.text)
        report = next(row for row in reports.json() if row["id"] == str(self.report.id))
        self.assertTrue(report["needs_review"])


if __name__ == "__main__":
    unittest.main()
