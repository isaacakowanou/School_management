import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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

    def _create_student_with_course_result_no_report(self) -> Student:
        student = Student(
            first_name="New",
            last_name="Student",
            grade_level="Grade 12",
            student_number="LIST-FIRST-REPORT",
        )
        course = Course(
            name="First Report Course",
            code="COURSE-FIRST-REPORT",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Spring",
            school_year="2026-2027",
        )
        self.db.add_all([student, course])
        self.db.flush()
        self.db.add(StudentParent(student=student, parent=self.parent, relationship="Guardian"))
        self.db.add(
            CourseResult(
                student=student,
                course=course,
                term="Spring",
                average=91.0,
                letter_grade="A",
                calculated_at=self.base_time,
            )
        )
        self.db.commit()
        self.db.refresh(student)
        return student

    def _create_student_with_tagged_course_results(self) -> Student:
        # Two FRENCH courses + one ENGLISH course so overall_average (all-courses
        # mean, 15.33) differs from bilingual_average (mean-of-track-means, 16.0).
        student = Student(
            first_name="Bilingual",
            last_name="Student",
            grade_level="Grade 12",
            student_number="LIST-BILINGUAL",
        )
        french_a = Course(
            name="Francais A", code="FR-BIL-A", teacher=self.teacher,
            grade_level="Grade 12", term="Spring", school_year="2026-2027",
            language_group="FRENCH",
        )
        french_b = Course(
            name="Francais B", code="FR-BIL-B", teacher=self.teacher,
            grade_level="Grade 12", term="Spring", school_year="2026-2027",
            language_group="FRENCH",
        )
        english = Course(
            name="English", code="EN-BIL", teacher=self.teacher,
            grade_level="Grade 12", term="Spring", school_year="2026-2027",
            language_group="ENGLISH",
        )
        self.db.add_all([student, french_a, french_b, english])
        self.db.flush()
        self.db.add_all(
            [
                CourseResult(student=student, course=french_a, term="Spring", average=12.0, letter_grade="C", scale="20", calculated_at=self.base_time),
                CourseResult(student=student, course=french_b, term="Spring", average=16.0, letter_grade="B", scale="20", calculated_at=self.base_time),
                CourseResult(student=student, course=english, term="Spring", average=18.0, letter_grade="A", scale="20", calculated_at=self.base_time),
            ]
        )
        self.db.commit()
        self.db.refresh(student)
        return student

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _report_course_snapshot(self, report_card_id) -> list[tuple[str, str, float, str]]:
        self.db.expire_all()
        report_card = self.db.get(ReportCard, report_card_id)
        return sorted(
            (
                str(course.course_id),
                course.course_name,
                course.average,
                course.letter_grade,
            )
            for course in report_card.courses
        )

    def _admin_report_list_item(self, report_card_id) -> dict:
        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))
        self.assertEqual(response.status_code, 200)
        reports_by_id = {report["id"]: report for report in response.json()}
        return reports_by_id[str(report_card_id)]

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

    def test_admin_can_edit_summary_on_approved_report_without_changing_snapshot(self):
        old_courses = self._report_course_snapshot(self.report_card.id)

        response = self.client.put(
            f"/api/v1/reports/{self.report_card.id}/summary",
            json={"ai_summary": "Updated parent summary."},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["ai_summary"], "Updated parent summary.")
        self.assertEqual(report["status"], "approved")
        self.assertEqual(report["overall_average"], 92.5)
        self.assertEqual(report["gpa"], 4.0)
        self.assertEqual(
            sorted(
                (
                    course["course_id"],
                    course["course_name"],
                    course["average"],
                    course["letter_grade"],
                )
                for course in report["courses"]
            ),
            old_courses,
        )

        self.db.expire_all()
        saved_report = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(saved_report.status, "approved")
        self.assertEqual(saved_report.overall_average, 92.5)
        self.assertEqual(saved_report.gpa, 4.0)
        self.assertEqual(self._report_course_snapshot(self.report_card.id), old_courses)
        audit_log = (
            self.db.query(AuditLog)
            .filter(
                AuditLog.action == "summary_edited",
                AuditLog.entity_id == self.report_card.id,
            )
            .one()
        )
        self.assertEqual(audit_log.old_value, {"ai_summary": "Strong work."})
        self.assertEqual(audit_log.new_value, {"ai_summary": "Updated parent summary."})

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(parent_response.json()["ai_summary"], "Updated parent summary.")

    def test_admin_can_edit_summary_on_sent_report_without_changing_status(self):
        self.report_card.status = "sent"
        self.report_card.sent_at = self.base_time + timedelta(hours=2)
        self.db.commit()

        response = self.client.put(
            f"/api/v1/reports/{self.report_card.id}/summary",
            json={"ai_summary": "Sent report summary update."},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["ai_summary"], "Sent report summary update.")
        self.assertEqual(report["status"], "sent")
        self.assertEqual(report["overall_average"], 92.5)
        self.assertEqual(report["gpa"], 4.0)

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(parent_response.json()["ai_summary"], "Sent report summary update.")

    def test_admin_can_edit_draft_summary_without_changing_parent_visibility(self):
        student = self._create_student_with_course_result_no_report()
        generate_response = self.client.post(
            f"/api/v1/reports/generate/{student.id}",
            json={"term": "Spring", "school_year": "2026-2027"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(generate_response.status_code, 201)
        report_id = generate_response.json()["id"]

        response = self.client.put(
            f"/api/v1/reports/{report_id}/summary",
            json={"ai_summary": "Draft parent summary."},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ai_summary"], "Draft parent summary.")
        self.assertEqual(response.json()["status"], "draft")

        parent_list_response = self.client.get(
            f"/api/v1/reports/student/{student.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_list_response.status_code, 200)
        self.assertEqual(parent_list_response.json(), [])

        parent_detail_response = self.client.get(
            f"/api/v1/reports/{report_id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_detail_response.status_code, 403)

    def test_summary_edit_does_not_clear_needs_review_or_staleness(self):
        self.course_result.average = 84.0
        self.course_result.letter_grade = "B"
        self.course_result.calculated_at = self.base_time + timedelta(hours=2)
        self.db.commit()

        self.assertTrue(self._admin_report_list_item(self.report_card.id)["needs_review"])
        before_staleness = self.client.get(
            f"/api/v1/reports/{self.report_card.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(before_staleness.status_code, 200)
        self.assertTrue(before_staleness.json()["is_stale"])

        response = self.client.put(
            f"/api/v1/reports/{self.report_card.id}/summary",
            json={"ai_summary": "Summary changed while stale."},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["ai_summary"], "Summary changed while stale.")
        self.assertEqual(report["status"], "approved")
        self.assertEqual(report["overall_average"], 92.5)
        self.assertEqual(report["gpa"], 4.0)
        self.assertTrue(self._admin_report_list_item(self.report_card.id)["needs_review"])

        after_staleness = self.client.get(
            f"/api/v1/reports/{self.report_card.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(after_staleness.status_code, 200)
        self.assertTrue(after_staleness.json()["is_stale"])

    def test_parent_cannot_edit_report_summary(self):
        response = self.client.put(
            f"/api/v1/reports/{self.report_card.id}/summary",
            json={"ai_summary": "Parent edit attempt."},
            headers=self._headers(self.parent_user.email),
        )

        self.assertEqual(response.status_code, 403)

    def test_draft_report_cannot_be_sent(self):
        self.report_card.status = "draft"
        self.report_card.approved_at = None
        self.report_card.approved_by_admin_id = None
        self.db.commit()

        with patch("routes.reports.send_report_notification_to_parents") as send_mock:
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Only approved or sent reports can be sent")
        send_mock.assert_not_called()

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 403)

    def test_approved_report_send_marks_sent_and_audits_provider_results(self):
        send_results = [
            {
                "email": self.parent_user.email,
                "sent": True,
                "success": True,
                "provider": "resend",
                "provider_message_id": "resend-message-1",
                "error": None,
            }
        ]

        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_card_id"], str(self.report_card.id))
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["sent_count"], 1)
        self.assertEqual(data["failed_count"], 0)
        self.assertEqual(data["results"], send_results)

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "sent")
        self.assertIsNotNone(report_card.sent_at)
        audit_log = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_sent", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit_log.old_value, {"status": "approved", "sent_at": None})
        self.assertEqual(audit_log.new_value["status"], "sent")
        self.assertIsNotNone(audit_log.new_value["sent_at"])
        self.assertEqual(audit_log.new_value["recipient_count"], 1)
        self.assertEqual(audit_log.new_value["success_count"], 1)
        self.assertEqual(audit_log.new_value["failed_count"], 0)
        self.assertEqual(audit_log.new_value["provider"], "resend")
        self.assertEqual(audit_log.new_value["provider_message_ids"], ["resend-message-1"])
        self.assertFalse(audit_log.new_value["was_already_sent"])

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(parent_response.json()["status"], "sent")

    def test_partial_send_marks_sent_and_tracks_failures(self):
        send_results = [
            {
                "email": self.parent_user.email,
                "sent": True,
                "success": True,
                "provider": "resend",
                "provider_message_id": "resend-message-1",
                "error": None,
            },
            {
                "email": "other-parent@example.test",
                "sent": False,
                "success": False,
                "provider": "resend",
                "provider_message_id": None,
                "error": "Mailbox unavailable",
            },
        ]

        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "sent")
        self.assertEqual(response.json()["sent_count"], 1)
        self.assertEqual(response.json()["failed_count"], 1)

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "sent")
        audit_log = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_sent", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit_log.new_value["recipient_count"], 2)
        self.assertEqual(audit_log.new_value["success_count"], 1)
        self.assertEqual(audit_log.new_value["failed_count"], 1)
        self.assertFalse(audit_log.new_value["was_already_sent"])

    def test_sent_report_can_be_resent_and_updates_sent_at_and_audits(self):
        old_sent_at = self.base_time + timedelta(hours=2)
        self.report_card.status = "sent"
        self.report_card.sent_at = old_sent_at
        self.db.commit()
        send_results = [
            {
                "email": self.parent_user.email,
                "sent": True,
                "success": True,
                "provider": "resend",
                "provider_message_id": "resend-message-2",
                "error": None,
            }
        ]

        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["sent_count"], 1)
        self.assertEqual(data["failed_count"], 0)

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "sent")
        self.assertIsNotNone(report_card.sent_at)
        self.assertNotEqual(report_card.sent_at, old_sent_at)
        audit_log = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_resent", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit_log.old_value, {"status": "sent", "sent_at": old_sent_at.isoformat()})
        self.assertEqual(audit_log.new_value["status"], "sent")
        self.assertIsNotNone(audit_log.new_value["sent_at"])
        self.assertEqual(audit_log.new_value["recipient_count"], 1)
        self.assertEqual(audit_log.new_value["success_count"], 1)
        self.assertEqual(audit_log.new_value["failed_count"], 0)
        self.assertEqual(audit_log.new_value["provider"], "resend")
        self.assertEqual(audit_log.new_value["provider_message_ids"], ["resend-message-2"])
        self.assertTrue(audit_log.new_value["was_already_sent"])

    def test_all_send_failures_do_not_mark_sent_and_create_failed_audit(self):
        send_results = [
            {
                "email": self.parent_user.email,
                "sent": False,
                "success": False,
                "provider": "resend",
                "provider_message_id": None,
                "error": "Provider rejected request",
            }
        ]

        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["message"], "No report notifications were sent")
        self.assertEqual(response.json()["detail"]["results"], send_results)

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "approved")
        self.assertIsNone(report_card.sent_at)
        audit_log = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_email_failed", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit_log.old_value, {"status": "approved", "sent_at": None})
        self.assertEqual(audit_log.new_value["recipient_count"], 1)
        self.assertEqual(audit_log.new_value["failed_count"], 1)
        self.assertEqual(audit_log.new_value["provider"], "resend")
        self.assertEqual(audit_log.new_value["errors"], ["Provider rejected request"])
        self.assertFalse(audit_log.new_value["was_already_sent"])

        parent_response = self.client.get(
            f"/api/v1/reports/{self.report_card.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(parent_response.json()["status"], "approved")

    def test_all_resend_failures_do_not_update_sent_at(self):
        old_sent_at = self.base_time + timedelta(hours=2)
        self.report_card.status = "sent"
        self.report_card.sent_at = old_sent_at
        self.db.commit()
        send_results = [
            {
                "email": self.parent_user.email,
                "sent": False,
                "success": False,
                "provider": "resend",
                "provider_message_id": None,
                "error": "Provider rejected request",
            }
        ]

        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post(
                f"/api/v1/reports/{self.report_card.id}/send",
                headers=self._headers(self.admin_user.email),
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["message"], "No report notifications were sent")

        self.db.expire_all()
        report_card = self.db.get(ReportCard, self.report_card.id)
        self.assertEqual(report_card.status, "sent")
        self.assertEqual(report_card.sent_at, old_sent_at)
        audit_log = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_email_failed", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit_log.old_value, {"status": "sent", "sent_at": old_sent_at.isoformat()})
        self.assertEqual(audit_log.new_value["recipient_count"], 1)
        self.assertEqual(audit_log.new_value["failed_count"], 1)
        self.assertEqual(audit_log.new_value["provider"], "resend")
        self.assertEqual(audit_log.new_value["errors"], ["Provider rejected request"])
        self.assertTrue(audit_log.new_value["was_already_sent"])

    def test_generated_first_report_is_draft_until_admin_approves(self):
        student = self._create_student_with_course_result_no_report()

        generate_response = self.client.post(
            f"/api/v1/reports/generate/{student.id}",
            json={"term": "Spring", "school_year": "2026-2027"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(generate_response.status_code, 201)
        report = generate_response.json()
        self.assertEqual(report["student_id"], str(student.id))
        self.assertEqual(report["term"], "Spring")
        self.assertEqual(report["school_year"], "2026-2027")
        self.assertEqual(report["overall_average"], 91.0)
        self.assertEqual(report["status"], "draft")

        parent_draft_list_response = self.client.get(
            f"/api/v1/reports/student/{student.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_draft_list_response.status_code, 200)
        self.assertEqual(parent_draft_list_response.json(), [])

        parent_draft_detail_response = self.client.get(
            f"/api/v1/reports/{report['id']}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_draft_detail_response.status_code, 403)

        approve_response = self.client.post(
            f"/api/v1/reports/{report['id']}/approve",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["status"], "approved")

        parent_approved_list_response = self.client.get(
            f"/api/v1/reports/student/{student.id}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_approved_list_response.status_code, 200)
        self.assertEqual(len(parent_approved_list_response.json()), 1)
        self.assertEqual(parent_approved_list_response.json()[0]["id"], report["id"])

        parent_approved_detail_response = self.client.get(
            f"/api/v1/reports/{report['id']}",
            headers=self._headers(self.parent_user.email),
        )
        self.assertEqual(parent_approved_detail_response.status_code, 200)

    def test_generate_report_exposes_language_averages(self):
        student = self._create_student_with_tagged_course_results()

        response = self.client.post(
            f"/api/v1/reports/generate/{student.id}",
            json={"term": "Spring", "school_year": "2026-2027"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        report = response.json()
        self.assertEqual(report["french_average"], 14.0)
        self.assertEqual(report["english_average"], 18.0)
        self.assertEqual(report["bilingual_average"], 16.0)
        # overall_average is still populated (legacy all-courses mean).
        self.assertEqual(report["overall_average"], 15.33)

    def test_regenerate_updates_language_averages(self):
        student = self._create_student_with_tagged_course_results()
        generate_response = self.client.post(
            f"/api/v1/reports/generate/{student.id}",
            json={"term": "Spring", "school_year": "2026-2027"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(generate_response.status_code, 201)
        report_id = generate_response.json()["id"]
        self.assertEqual(generate_response.json()["english_average"], 18.0)
        self.assertEqual(generate_response.json()["bilingual_average"], 16.0)

        english_result = (
            self.db.query(CourseResult).join(Course).filter(Course.code == "EN-BIL").one()
        )
        english_result.average = 10.0
        self.db.commit()

        regenerate_response = self.client.post(
            f"/api/v1/reports/{report_id}/regenerate",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(regenerate_response.status_code, 200)
        regenerated = regenerate_response.json()
        self.assertEqual(regenerated["french_average"], 14.0)
        self.assertEqual(regenerated["english_average"], 10.0)
        self.assertEqual(regenerated["bilingual_average"], 12.0)

        self.db.expire_all()
        saved = self.db.get(ReportCard, UUID(report_id))
        self.assertEqual(saved.french_average, 14.0)
        self.assertEqual(saved.english_average, 10.0)
        self.assertEqual(saved.bilingual_average, 12.0)

    def test_admin_report_list_shows_bilingual_average_for_new_report(self):
        student = self._create_student_with_tagged_course_results()
        generate_response = self.client.post(
            f"/api/v1/reports/generate/{student.id}",
            json={"term": "Spring", "school_year": "2026-2027"},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(generate_response.status_code, 201)
        report_id = generate_response.json()["id"]

        item = self._admin_report_list_item(report_id)
        self.assertEqual(item["bilingual_average"], 16.0)

    def test_historical_report_exposes_null_language_averages(self):
        # self.report_card predates A1.6 (created without the three averages).
        detail_response = self.client.get(
            f"/api/v1/reports/admin/{self.report_card.id}",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(detail_response.status_code, 200)
        report = detail_response.json()
        self.assertIsNone(report["french_average"])
        self.assertIsNone(report["english_average"])
        self.assertIsNone(report["bilingual_average"])
        # Legacy overall_average is still present so the frontend fallback works.
        self.assertEqual(report["overall_average"], 92.5)

        item = self._admin_report_list_item(self.report_card.id)
        self.assertIsNone(item["bilingual_average"])


if __name__ == "__main__":
    unittest.main()
