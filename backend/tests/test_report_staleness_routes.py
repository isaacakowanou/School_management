import unittest
from datetime import datetime, timezone

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
    Parent,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)


class ReportStalenessRouteTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-stale@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-stale@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-stale@example.test", role="teacher")
        self.db.flush()

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-STALENESS")
        self.student = Student(
            first_name="Demo",
            last_name="Student",
            grade_level="Grade 12",
            student_number="STALE001",
        )
        self.db.add_all([self.parent, self.teacher, self.student])
        self.db.flush()
        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))

        self.math = Course(
            name="Mathematics",
            code="MATH-ST",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.science = Course(
            name="Science",
            code="SCI-ST",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add_all([self.math, self.science])
        self.db.flush()

        self.math_result = CourseResult(
            student=self.student,
            course=self.math,
            term="Fall",
            average=19.0,
            letter_grade="A",
        )
        self.science_result = CourseResult(
            student=self.student,
            course=self.science,
            term="Fall",
            average=17.0,
            letter_grade="B",
        )
        self.db.add_all([self.math_result, self.science_result])
        self.db.flush()

        approved_at = datetime.now(timezone.utc)
        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=18.0,
            gpa=3.5,
            status="sent",
            ai_summary="Keep this summary.",
            pdf_url="/old/local/path.pdf",
            approved_by_admin_id=self.admin_user.id,
            approved_at=approved_at,
            sent_at=approved_at,
        )
        self.db.add(self.report_card)
        self.db.flush()
        self.db.add_all(
            [
                ReportCardCourse(
                    report_card_id=self.report_card.id,
                    course_id=self.math.id,
                    course_name="Mathematics",
                    average=19.0,
                    letter_grade="A",
                ),
                ReportCardCourse(
                    report_card_id=self.report_card.id,
                    course_id=self.science.id,
                    course_name="Science",
                    average=17.0,
                    letter_grade="B",
                ),
            ]
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

    def _make_report_stale(self) -> None:
        self.math_result.average = 15.0
        self.math_result.letter_grade = "C"
        self.db.commit()

    def test_admin_gets_report_staleness(self):
        self._make_report_stale()

        response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_stale"])
        self.assertIn("overall_average changed", data["reason"])
        self.assertEqual(data["snapshot_overall_average"], 18.0)
        self.assertEqual(data["current_overall_average"], 16.0)
        self.assertEqual(data["snapshot_gpa"], 3.5)
        self.assertEqual(data["current_gpa"], 2.5)

    def test_report_response_includes_scale_for_historical_report(self):
        self.report_card.scale = "100"
        self.db.commit()

        response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scale"], "100")

    def test_regenerating_scale_100_report_sets_scale_20(self):
        # Mark the report as a historical /100 snapshot, then regenerate from the
        # current /20 course results.
        self.report_card.scale = "100"
        self.report_card.overall_average = 90.0
        self.db.commit()

        response = self.client.post(
            f"/api/v1/reports/{self.report_card.id}/regenerate",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scale"], "20")
        # Current results are 19.0 and 17.0 on /20 -> overall 18.0
        self.assertEqual(data["overall_average"], 18.0)

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.scale, "20")

    def test_historical_scale_100_report_is_not_stale_when_data_unchanged(self):
        # A pre-A1.2 report has scale="100" and stores /100 averages in both the
        # ReportCard and ReportCardCourse rows. The staleness check must normalize
        # the snapshot to /20 before comparing against the builder's /20 output,
        # otherwise every historical report falsely appears stale on deploy.
        historical_student = Student(
            first_name="Legacy",
            last_name="Student",
            grade_level="Grade 10",
            student_number="LEGACY001",
        )
        self.db.add(historical_student)
        self.db.flush()

        # CourseResults tagged scale="100" — values 92.5 and 87.5 are on the /100 scale.
        self.db.add_all([
            CourseResult(
                student=historical_student,
                course=self.math,
                term="Fall",
                average=92.5,
                letter_grade="A",
                scale="100",
            ),
            CourseResult(
                student=historical_student,
                course=self.science,
                term="Fall",
                average=87.5,
                letter_grade="B",
                scale="100",
            ),
        ])
        self.db.flush()

        # ReportCard snapshot on the /100 scale: overall = (92.5 + 87.5) / 2 = 90.0
        approved_at = datetime.now(timezone.utc)
        historical_report = ReportCard(
            student=historical_student,
            term="Fall",
            school_year="2026-2027",
            overall_average=90.0,
            gpa=3.5,
            scale="100",
            status="approved",
            approved_by_admin_id=self.admin_user.id,
            approved_at=approved_at,
        )
        self.db.add(historical_report)
        self.db.flush()
        self.db.add_all([
            ReportCardCourse(
                report_card_id=historical_report.id,
                course_id=self.math.id,
                course_name="Mathematics",
                average=92.5,
                letter_grade="A",
            ),
            ReportCardCourse(
                report_card_id=historical_report.id,
                course_id=self.science.id,
                course_name="Science",
                average=87.5,
                letter_grade="B",
            ),
        ])
        self.db.commit()
        self.db.refresh(historical_report)

        # Underlying data is unchanged — must not be stale.
        # Builder normalizes 92.5 → 18.5 and 87.5 → 17.5 (/20); overall = 18.0.
        # Staleness check normalizes snapshot 90.0 → 18.0 and compares 18.0 == 18.0.
        response = self.client.get(
            f"/api/v1/reports/{historical_report.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_stale"], msg=f"Expected not stale; reasons: {data.get('reason')}")

        # Now change a CourseResult — the report should become stale.
        math_result = self.db.scalar(
            select(CourseResult).where(
                CourseResult.student_id == historical_student.id,
                CourseResult.course_id == self.math.id,
            )
        )
        math_result.average = 60.0  # Still /100; normalizes to 12.0 /20
        self.db.commit()

        response = self.client.get(
            f"/api/v1/reports/{historical_report.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_stale"])
        self.assertIn("overall_average changed", data["reason"])

    def test_parent_and_teacher_cannot_get_report_staleness(self):
        for email in [self.parent_user.email, self.teacher_user.email]:
            response = self.client.get(
                f"/api/v1/reports/{self.report_card.id}/staleness",
                headers=self._headers(email),
            )
            self.assertEqual(response.status_code, 403)

    def test_admin_regenerates_report_snapshot_and_parent_cannot_view_draft(self):
        self._make_report_stale()

        response = self.client.post(
            f"/api/v1/reports/{self.report_card.id}/regenerate",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["overall_average"], 16.0)
        self.assertEqual(data["gpa"], 2.5)
        self.assertEqual(data["ai_summary"], "Keep this summary.")
        courses_by_name = {course["course_name"]: course for course in data["courses"]}
        self.assertEqual(courses_by_name["Mathematics"]["average"], 15.0)
        self.assertEqual(courses_by_name["Mathematics"]["letter_grade"], "C")

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "draft")
        self.assertIsNone(report_card.approved_by_admin_id)
        self.assertIsNone(report_card.approved_at)
        self.assertIsNone(report_card.sent_at)
        self.assertEqual(report_card.ai_summary, "Keep this summary.")
        report_courses = self.db.scalars(
            select(ReportCardCourse).where(ReportCardCourse.report_card_id == report_card.id)
        ).all()
        self.assertEqual(len(report_courses), 2)

        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "report_regenerated",
                AuditLog.entity_id == report_card.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(audit_log.old_value["status"], "sent")
        self.assertEqual(audit_log.new_value["status"], "draft")

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
