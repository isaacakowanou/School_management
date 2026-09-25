import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import create_user_access_token
from database import get_db
from main import app
from models import (
    AuditLog,
    Base,
    Course,
    Enrollment,
    Grade,
    GradeItem,
    Parent,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    Teacher,
    User,
)
from services.email_service import send_grades_notification


EMAIL_CONFIG = {
    "provider": "resend",
    "resend_api_key": "test-key",
    "email_from": "school@example.test",
    "app_base_url": "https://portal.example.test",
}

SMS_CONFIG = {
    "account_sid": "sid",
    "auth_token": "token",
    "verify_service_sid": "verify",
    "phone_number": "+15550000000",
    "app_base_url": "https://portal.example.test",
}


class GradeNotificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.SessionLocal()

        self.teacher_user = User(
            name="ZZ-TEST-Teacher",
            email="zz-test-teacher@example.test",
            password_hash="hash",
            role="teacher",
        )
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-T001")
        self.course = Course(
            name="ZZ-TEST-Course",
            code="ZZ-TEST-NOTIFY",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.student = Student(
            first_name="ZZ-TEST",
            last_name="Student",
            student_number="ZZ-TEST-S001",
        )
        self.grade_item = GradeItem(
            course=self.course,
            title="ZZ-TEST-Item",
            category="Quiz",
            max_score=20,
            weight=1,
            term="1er Trimestre",
        )
        self.parent_user = User(
            name="ZZ-TEST-Parent",
            email="zz-test-parent@example.test",
            password_hash="hash",
            role="parent",
        )
        self.parent = Parent(user=self.parent_user, phone="9705550100")
        self.db.add_all(
            [
                self.course,
                self.student,
                self.grade_item,
                self.parent,
                Enrollment(student=self.student, course=self.course),
                StudentParent(student=self.student, parent=self.parent, relationship="guardian"),
            ]
        )
        self.db.commit()

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_user_access_token(self.teacher_user)}"}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_report(self, status="approved", *, term="1er Trimestre", school_year="2026-2027"):
        report = ReportCard(
            student=self.student,
            term=term,
            school_year=school_year,
            overall_average=14,
            status=status,
            approved_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        self.db.add(report)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card=report,
                course=self.course,
                course_name=self.course.name,
                average=14,
                letter_grade="B",
            )
        )
        self.db.commit()
        return report

    def create_post_approval_grade(self):
        grade = Grade(
            student=self.student,
            grade_item=self.grade_item,
            score=14,
            submitted_by_teacher=self.teacher,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(grade)
        self.db.commit()
        return grade

    def delete_report_fixture(self, report):
        for course_snapshot in list(report.courses):
            self.db.delete(course_snapshot)
        self.db.delete(report)
        self.db.commit()

    @patch("services.sms_service.send_grades_available_sms")
    @patch("services.sms_service._get_messaging_config", return_value=SMS_CONFIG)
    @patch("services.email_service._get_email_config", side_effect=ValueError("missing email"))
    @patch("services.email_service.send_grade_notification_email")
    def test_missing_email_config_still_delivers_phone_channels(
        self, email_send, _email_config, _sms_config, sms_send
    ):
        sms_send.return_value = [
            {"channel": "sms", "sent": True},
            {"channel": "whatsapp", "sent": True},
        ]

        result = send_grades_notification(self.db, self.course, self.student)

        email_send.assert_not_called()
        sms_send.assert_called_once()
        self.assertEqual(result["recipients"], 1)
        self.assertEqual(result["delivered"], {"email": 0, "sms": 2})
        self.assertEqual(result["failed"], {"email": 0, "sms": 0})
        self.assertEqual(result["skipped"], {"email": 1, "sms": 0})

    @patch("services.sms_service.send_grades_available_sms")
    @patch("services.sms_service._get_messaging_config", return_value=SMS_CONFIG)
    @patch("services.email_service._get_email_config", return_value=EMAIL_CONFIG)
    @patch("services.email_service.send_grade_notification_email")
    def test_mixed_channel_outcomes_are_counted(
        self, email_send, _email_config, _sms_config, sms_send
    ):
        email_send.return_value = {"sent": True}
        sms_send.return_value = [
            {"channel": "sms", "sent": True},
            {"channel": "whatsapp", "sent": False},
        ]

        result = send_grades_notification(self.db, self.course, self.student)

        self.assertEqual(result["delivered"], {"email": 1, "sms": 1})
        self.assertEqual(result["failed"], {"email": 0, "sms": 1})
        self.assertEqual(result["skipped"], {"email": 0, "sms": 0})

    @patch("services.sms_service.send_grades_available_sms")
    @patch("services.sms_service._get_messaging_config", return_value=SMS_CONFIG)
    @patch("services.email_service._get_email_config", return_value=EMAIL_CONFIG)
    @patch("services.email_service.send_grade_notification_email")
    def test_africastalking_sms_attempt_and_whatsapp_skip_are_counted(
        self, email_send, _email_config, _sms_config, sms_send
    ):
        email_send.return_value = {"sent": True}
        sms_send.return_value = [
            {
                "provider": "africastalking",
                "channel": "sms",
                "sent": True,
                "skipped": False,
            },
            {
                "provider": "africastalking",
                "channel": "whatsapp",
                "sent": False,
                "skipped": True,
            },
        ]

        result = send_grades_notification(self.db, self.course, self.student)

        sms_send.assert_called_once()
        self.assertEqual(result["delivered"], {"email": 1, "sms": 1})
        self.assertEqual(result["failed"], {"email": 0, "sms": 0})
        self.assertEqual(result["skipped"], {"email": 0, "sms": 1})

    @patch("services.sms_service.send_grades_available_sms")
    @patch("services.sms_service.send_grade_correction_sms")
    @patch("services.sms_service._get_messaging_config", return_value=SMS_CONFIG)
    @patch("services.email_service._get_email_config", return_value=EMAIL_CONFIG)
    @patch("services.email_service.send_grade_notification_email")
    @patch("services.email_service.send_grade_correction_email")
    def test_correction_dispatch_uses_only_correction_copy(
        self,
        correction_email,
        generic_email,
        _email_config,
        _sms_config,
        correction_sms,
        generic_sms,
    ):
        correction_email.return_value = {"sent": True}
        correction_sms.return_value = [{"channel": "sms", "sent": True}]

        result = send_grades_notification(
            self.db,
            self.course,
            self.student,
            correction=True,
            term="1er Trimestre",
        )

        correction_email.assert_called_once()
        correction_sms.assert_called_once()
        generic_email.assert_not_called()
        generic_sms.assert_not_called()
        self.assertEqual(result["delivered"], {"email": 1, "sms": 1})

    @patch("services.sms_service.send_grades_available_sms")
    @patch("services.sms_service._get_messaging_config", return_value=SMS_CONFIG)
    @patch("services.email_service._get_email_config", return_value=EMAIL_CONFIG)
    @patch("services.email_service.send_grade_notification_email")
    def test_legacy_duplicate_links_notify_each_parent_once(
        self, email_send, _email_config, _sms_config, sms_send
    ):
        self.db.execute(text("DROP INDEX uq_active_student_parent"))
        self.db.add(
            StudentParent(student=self.student, parent=self.parent, relationship="guardian")
        )
        self.db.commit()
        email_send.return_value = {"sent": True}
        sms_send.return_value = [{"channel": "sms", "sent": True}]

        result = send_grades_notification(self.db, self.course, self.student)

        self.assertEqual(result["recipients"], 1)
        email_send.assert_called_once()
        sms_send.assert_called_once()

    @patch("routes.grades.send_grades_notification")
    def test_all_failure_response_is_audited_and_saved_grade_remains(self, send_notification):
        save_response = self.client.post(
            f"/api/v1/courses/{self.course.id}/grades/batch",
            json={
                "entries": [
                    {
                        "student_id": str(self.student.id),
                        "grade_item_id": str(self.grade_item.id),
                        "score": 14,
                    }
                ]
            },
            headers=self.headers,
        )
        self.assertEqual(save_response.status_code, 200)

        send_notification.return_value = {
            "recipients": 1,
            "delivered": {"email": 0, "sms": 0},
            "failed": {"email": 1, "sms": 2},
            "skipped": {"email": 0, "sms": 0},
        }
        response = self.client.post(
            f"/api/v1/courses/{self.course.id}/notify-grades",
            json={"student_ids": [str(self.student.id)]},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["delivered"], {"email": 0, "sms": 0})
        self.assertEqual(response.json()["failed"], {"email": 1, "sms": 2})
        self.assertIsNotNone(
            self.db.scalar(
                select(Grade).where(
                    Grade.student_id == self.student.id,
                    Grade.grade_item_id == self.grade_item.id,
                    Grade.deleted_at.is_(None),
                )
            )
        )
        audit = self.db.scalar(
            select(AuditLog).where(AuditLog.action == "grade_notifications_failed")
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_value["failed"], {"email": 1, "sms": 2})

    @patch("routes.grades.send_grades_notification")
    def test_approved_or_sent_report_with_post_approval_write_uses_correction_copy(
        self, send_notification
    ):
        send_notification.return_value = {
            "recipients": 1,
            "delivered": {"email": 1, "sms": 1},
            "failed": {"email": 0, "sms": 0},
            "skipped": {"email": 0, "sms": 0},
        }
        self.create_post_approval_grade()

        for status in ("approved", "sent"):
            with self.subTest(status=status):
                report = self.create_report(status=status)
                response = self.client.post(
                    f"/api/v1/courses/{self.course.id}/notify-grades",
                    json={
                        "student_ids": [str(self.student.id)],
                        "term": "1er Trimestre",
                    },
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(send_notification.call_args.kwargs["correction"])
                self.assertEqual(send_notification.call_args.kwargs["term"], "1er Trimestre")
                self.delete_report_fixture(report)

    @patch("routes.grades.send_grades_notification")
    def test_draft_and_needs_review_reports_use_generic_grade_notice(self, send_notification):
        send_notification.return_value = {
            "recipients": 1,
            "delivered": {"email": 1, "sms": 0},
            "failed": {"email": 0, "sms": 0},
            "skipped": {"email": 0, "sms": 1},
        }
        self.create_post_approval_grade()

        for status in ("draft", "needs_review"):
            with self.subTest(status=status):
                report = self.create_report(status=status)
                response = self.client.post(
                    f"/api/v1/courses/{self.course.id}/notify-grades",
                    json={"student_ids": [str(self.student.id)], "term": "1er Trimestre"},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(send_notification.call_args.kwargs["correction"])
                self.delete_report_fixture(report)

    @patch("routes.grades.send_grades_notification")
    def test_duplicate_student_ids_send_one_notification(self, send_notification):
        send_notification.return_value = {
            "recipients": 1,
            "delivered": {"email": 1, "sms": 0},
            "failed": {"email": 0, "sms": 0},
            "skipped": {"email": 0, "sms": 1},
        }

        response = self.client.post(
            f"/api/v1/courses/{self.course.id}/notify-grades",
            json={"student_ids": [str(self.student.id), str(self.student.id)]},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        send_notification.assert_called_once()


if __name__ == "__main__":
    unittest.main()
