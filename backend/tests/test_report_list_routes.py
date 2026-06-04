import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
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


class ReportListRouteTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-list@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-list@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-list@example.test", role="teacher")
        self.db.flush()
        self.base_time = datetime.now() - timedelta(days=5)

        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-LIST-1")
        self.student = Student(
            first_name="Ada",
            last_name="Lovelace",
            grade_level="Grade 12",
            student_number="LIST001",
        )
        self.db.add_all([self.parent, self.teacher, self.student])
        self.db.flush()
        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))

        self.course = Course(
            name="Mathematics",
            code="MATH-LIST",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()
        self.course_result = CourseResult(
            student=self.student,
            course=self.course,
            term="Fall",
            average=92.5,
            letter_grade="A",
            calculated_at=self.base_time,
        )
        self.db.add(self.course_result)
        self.db.flush()

        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=92.5,
            gpa=4.0,
            status="approved",
            ai_summary="Strong work.",
            approved_by_admin_id=self.admin_user.id,
            approved_at=self.base_time + timedelta(hours=1),
        )
        self.db.add(self.report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=self.report_card.id,
                course_id=self.course.id,
                course_name="Mathematics",
                average=92.5,
                letter_grade="A",
            )
        )
        self.db.commit()
        self.db.refresh(self.report_card)

    def _create_report_with_course_result(
        self,
        *,
        suffix: str,
        status: str,
        approved_at: datetime | None,
        calculated_at: datetime,
        created_at: datetime | None = None,
    ) -> ReportCard:
        student = Student(
            first_name="Student",
            last_name=suffix,
            grade_level="Grade 12",
            student_number=f"LIST-{suffix}",
        )
        course = Course(
            name=f"Course {suffix}",
            code=f"COURSE-{suffix}",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add_all([student, course])
        self.db.flush()

        self.db.add(
            CourseResult(
                student=student,
                course=course,
                term="Fall",
                average=88.0,
                letter_grade="B",
                calculated_at=calculated_at,
            )
        )
        report_values = {
            "student": student,
            "term": "Fall",
            "school_year": "2026-2027",
            "overall_average": 88.0,
            "gpa": 3.0,
            "status": status,
            "approved_by_admin_id": self.admin_user.id if approved_at is not None else None,
            "approved_at": approved_at,
        }
        if created_at is not None:
            report_values["created_at"] = created_at
        report_card = ReportCard(**report_values)
        self.db.add(report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=report_card.id,
                course_id=course.id,
                course_name=course.name,
                average=88.0,
                letter_grade="B",
            )
        )
        self.db.commit()
        self.db.refresh(report_card)
        return report_card

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_admin_report_list_includes_student_display_fields(self):
        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        report = data[0]
        self.assertEqual(report["id"], str(self.report_card.id))
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertEqual(report["student_name"], "Ada Lovelace")
        self.assertEqual(report["student_number"], "LIST001")
        self.assertEqual(report["term"], "Fall")
        self.assertEqual(report["school_year"], "2026-2027")
        self.assertEqual(report["status"], "approved")
        self.assertEqual(report["overall_average"], 92.5)
        self.assertEqual(report["gpa"], 4.0)
        self.assertIn("created_at", report)
        self.assertFalse(report["needs_review"])
        self.assertNotIn("courses", report)

    def test_admin_report_detail_includes_student_display_fields(self):
        response = self.client.get(
            f"/api/v1/reports/admin/{self.report_card.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["id"], str(self.report_card.id))
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertEqual(report["student_name"], "Ada Lovelace")
        self.assertEqual(report["student_number"], "LIST001")
        self.assertEqual(report["term"], "Fall")
        self.assertEqual(report["school_year"], "2026-2027")
        self.assertEqual(report["status"], "approved")
        self.assertIn("courses", report)

    def test_parent_cannot_access_admin_report_detail(self):
        response = self.client.get(
            f"/api/v1/reports/admin/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_needs_review_true_when_course_result_calculated_after_approval(self):
        report_card = self._create_report_with_course_result(
            suffix="STALE",
            status="approved",
            approved_at=self.base_time,
            calculated_at=self.base_time + timedelta(hours=1),
        )

        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        reports_by_id = {report["id"]: report for report in response.json()}
        self.assertTrue(reports_by_id[str(report_card.id)]["needs_review"])

    def test_needs_review_false_when_course_result_calculated_before_or_at_approval(self):
        older_report = self._create_report_with_course_result(
            suffix="OLDER",
            status="approved",
            approved_at=self.base_time + timedelta(hours=1),
            calculated_at=self.base_time,
        )
        equal_report = self._create_report_with_course_result(
            suffix="EQUAL",
            status="approved",
            approved_at=self.base_time,
            calculated_at=self.base_time,
        )

        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        reports_by_id = {report["id"]: report for report in response.json()}
        self.assertFalse(reports_by_id[str(older_report.id)]["needs_review"])
        self.assertFalse(reports_by_id[str(equal_report.id)]["needs_review"])

    def test_needs_review_false_for_draft_even_when_course_result_is_newer(self):
        report_card = self._create_report_with_course_result(
            suffix="DRAFT",
            status="draft",
            approved_at=self.base_time,
            calculated_at=self.base_time + timedelta(hours=1),
        )

        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        reports_by_id = {report["id"]: report for report in response.json()}
        self.assertFalse(reports_by_id[str(report_card.id)]["needs_review"])

    def test_needs_review_true_for_sent_report_when_course_result_is_newer(self):
        report_card = self._create_report_with_course_result(
            suffix="SENT",
            status="sent",
            approved_at=self.base_time,
            calculated_at=self.base_time + timedelta(hours=1),
        )

        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        reports_by_id = {report["id"]: report for report in response.json()}
        self.assertTrue(reports_by_id[str(report_card.id)]["needs_review"])

    def test_needs_review_false_after_regenerate_and_reapprove(self):
        self.course_result.average = 84.0
        self.course_result.letter_grade = "B"
        self.course_result.calculated_at = self.base_time + timedelta(days=1)
        self.report_card.approved_at = self.base_time
        self.db.commit()

        before_response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))
        self.assertEqual(before_response.status_code, 200)
        before_by_id = {report["id"]: report for report in before_response.json()}
        self.assertTrue(before_by_id[str(self.report_card.id)]["needs_review"])

        regenerate_response = self.client.post(
            f"/api/v1/reports/{self.report_card.id}/regenerate",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(regenerate_response.status_code, 200)
        self.assertEqual(regenerate_response.json()["status"], "draft")

        approve_response = self.client.post(
            f"/api/v1/reports/{self.report_card.id}/approve",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["status"], "approved")

        after_response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))
        self.assertEqual(after_response.status_code, 200)
        after_by_id = {report["id"]: report for report in after_response.json()}
        self.assertFalse(after_by_id[str(self.report_card.id)]["needs_review"])

    def test_needs_review_reports_sort_above_non_review_reports(self):
        non_review_report = self._create_report_with_course_result(
            suffix="NEWER-NONREVIEW",
            status="approved",
            approved_at=self.base_time + timedelta(hours=2),
            calculated_at=self.base_time,
            created_at=self.base_time + timedelta(days=3),
        )
        review_report = self._create_report_with_course_result(
            suffix="OLDER-REVIEW",
            status="approved",
            approved_at=self.base_time,
            calculated_at=self.base_time + timedelta(hours=1),
            created_at=self.base_time,
        )

        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["id"], str(review_report.id))
        self.assertTrue(data[0]["needs_review"])
        non_review_index = [report["id"] for report in data].index(str(non_review_report.id))
        self.assertGreater(non_review_index, 0)
        self.assertFalse(data[non_review_index]["needs_review"])

    def test_parent_student_reports_keep_existing_shape(self):
        response = self.client.get(
            f"/api/v1/reports/student/{self.student.id}",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        report = data[0]
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertIn("courses", report)
        self.assertNotIn("student_name", report)
        self.assertNotIn("student_number", report)
        self.assertNotIn("needs_review", report)

    def test_parent_report_detail_keeps_existing_shape(self):
        response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["student_id"], str(self.student.id))
        self.assertIn("courses", report)
        self.assertNotIn("student_name", report)
        self.assertNotIn("student_number", report)
        self.assertNotIn("needs_review", report)


if __name__ == "__main__":
    unittest.main()
