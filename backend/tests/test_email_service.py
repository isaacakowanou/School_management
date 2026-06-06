import os
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Parent, ReportCard, Student, StudentParent, User
from services.email_service import send_report_available_email, send_report_notification_to_parents


EMAIL_ENV = {
    "EMAIL_PROVIDER": "smtp",
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "smtp-user",
    "SMTP_PASSWORD": "smtp-password",
    "SMTP_FROM_EMAIL": "school@example.test",
    "APP_BASE_URL": "https://portal.example.test",
}

RESEND_ENV = {
    "EMAIL_PROVIDER": "resend",
    "RESEND_API_KEY": "resend-api-key",
    "EMAIL_FROM": "school@example.test",
    "APP_BASE_URL": "https://portal.example.test",
}


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.student = Student(
            first_name="Isaac",
            last_name="Akowanou",
            grade_level="Grade 12",
            student_number="STU001",
        )
        self.parent_user = User(
            name="Parent One",
            email="parent@example.test",
            password_hash="hash",
            role="parent",
        )
        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=91.7,
            gpa=4.0,
            status="approved",
        )
        self.db.add_all([self.student, self.parent, self.report_card])
        self.db.flush()
        self.db.add(StudentParent(student_id=self.student.id, parent_id=self.parent.id, relationship="guardian"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_missing_smtp_config_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing email configuration"):
                send_report_notification_to_parents(self.db, self.report_card.id)

    def test_sends_resend_email_to_linked_parent_and_returns_structured_results(self):
        send_mock = MagicMock(return_value={"id": "resend-message-123"})
        fake_resend = SimpleNamespace(api_key=None, Emails=SimpleNamespace(send=send_mock))

        with patch.dict(os.environ, RESEND_ENV, clear=True):
            with patch.dict(sys.modules, {"resend": fake_resend}):
                results = send_report_notification_to_parents(self.db, self.report_card.id)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0],
            {
                "email": "parent@example.test",
                "sent": True,
                "success": True,
                "provider": "resend",
                "provider_message_id": "resend-message-123",
                "error": None,
            },
        )
        self.assertEqual(fake_resend.api_key, "resend-api-key")
        payload = send_mock.call_args.args[0]
        self.assertEqual(payload["from"], "school@example.test")
        self.assertEqual(payload["to"], ["parent@example.test"])
        self.assertEqual(payload["subject"], "Report card available")
        self.assertIn("A report card is available. Please log in to view it.", payload["text"])
        self.assertIn(f"https://portal.example.test/reports/{self.report_card.id}", payload["text"])
        self.assertNotIn("Isaac Akowanou", payload["text"])
        self.assertNotIn("91.7", payload["text"])
        self.assertNotIn("4.0", payload["text"])
        self.assertNotIn("attachments", payload)
        self.assertNotIn("pdf", payload["text"].lower())

    def test_sends_smtp_email_to_linked_parent_and_returns_results(self):
        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance

        with patch.dict(os.environ, EMAIL_ENV, clear=True):
            with patch("services.email_service.smtplib.SMTP", return_value=smtp_context) as smtp_class:
                results = send_report_notification_to_parents(self.db, self.report_card.id)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "parent@example.test")
        self.assertTrue(results[0]["sent"])
        self.assertTrue(results[0]["success"])
        self.assertEqual(results[0]["provider"], "smtp")
        self.assertIsNone(results[0]["provider_message_id"])
        self.assertIsNone(results[0]["error"])
        smtp_class.assert_called_once_with("smtp.example.test", 587)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("smtp-user", "smtp-password")
        smtp_instance.send_message.assert_called_once()

        message = smtp_instance.send_message.call_args.args[0]
        body = message.get_content()
        self.assertEqual(message["To"], "parent@example.test")
        self.assertEqual(message["From"], "school@example.test")
        self.assertIn("A report card is available. Please log in to view it.", body)
        self.assertIn(f"https://portal.example.test/reports/{self.report_card.id}", body)
        self.assertNotIn("Isaac Akowanou", body)
        self.assertNotIn("91.7", body)
        self.assertNotIn("4.0", body)
        self.assertNotIn("pdf", body.lower())
        self.assertFalse(message.is_multipart())

    def test_provider_errors_are_sanitized(self):
        config = {
            "provider": "resend",
            "resend_api_key": "secret-resend-key",
            "email_from": "school@example.test",
            "app_base_url": "https://portal.example.test",
        }

        with patch(
            "services.email_service._send_resend_email",
            side_effect=RuntimeError("Provider rejected secret-resend-key"),
        ):
            result = send_report_available_email(
                "parent@example.test",
                "Parent One",
                "https://portal.example.test/reports/report-id",
                config=config,
            )

        self.assertFalse(result["sent"])
        self.assertEqual(result["provider"], "resend")
        self.assertIn("[redacted]", result["error"])
        self.assertNotIn("secret-resend-key", result["error"])

    def test_smtp_username_and_password_are_sanitized(self):
        config = {
            "provider": "smtp",
            "smtp_host": "smtp.example.test",
            "smtp_port": 587,
            "smtp_username": "secret-smtp-user",
            "smtp_password": "secret-smtp-password",
            "smtp_from_email": "school@example.test",
            "app_base_url": "https://portal.example.test",
        }

        with patch(
            "services.email_service._send_smtp_email",
            side_effect=RuntimeError("Login failed for secret-smtp-user with secret-smtp-password"),
        ):
            result = send_report_available_email(
                "parent@example.test",
                "Parent One",
                "https://portal.example.test/reports/report-id",
                config=config,
            )

        self.assertFalse(result["sent"])
        self.assertEqual(result["provider"], "smtp")
        self.assertIn("[redacted]", result["error"])
        self.assertNotIn("secret-smtp-user", result["error"])
        self.assertNotIn("secret-smtp-password", result["error"])

    def test_blank_recipient_email_fails_without_provider_call(self):
        config = {
            "provider": "resend",
            "resend_api_key": "secret-resend-key",
            "email_from": "school@example.test",
            "app_base_url": "https://portal.example.test",
        }

        with patch("services.email_service._send_resend_email") as send_mock:
            result = send_report_available_email(
                "   ",
                "Parent One",
                "https://portal.example.test/reports/report-id",
                config=config,
            )

        send_mock.assert_not_called()
        self.assertEqual(
            result,
            {
                "email": None,
                "sent": False,
                "success": False,
                "provider": "resend",
                "provider_message_id": None,
                "error": "Parent email is missing",
            },
        )

    def test_continues_after_individual_email_failure(self):
        second_parent_user = User(
            name="Parent Two",
            email="parent2@example.test",
            password_hash="hash",
            role="parent",
        )
        second_parent = Parent(user=second_parent_user, phone="555-0101")
        self.db.add(second_parent)
        self.db.flush()
        self.db.add(StudentParent(student_id=self.student.id, parent_id=second_parent.id, relationship="guardian"))
        self.db.commit()

        smtp_instance = MagicMock()
        smtp_instance.send_message.side_effect = [RuntimeError("SMTP failure"), None]
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance

        with patch.dict(os.environ, EMAIL_ENV, clear=True):
            with patch("services.email_service.smtplib.SMTP", return_value=smtp_context):
                results = send_report_notification_to_parents(self.db, self.report_card.id)

        self.assertEqual(len(results), 2)
        self.assertEqual({result["email"] for result in results}, {"parent@example.test", "parent2@example.test"})
        failed_results = [result for result in results if not result["sent"]]
        successful_results = [result for result in results if result["sent"]]
        self.assertEqual(len(failed_results), 1)
        self.assertEqual(len(successful_results), 1)
        self.assertIn("SMTP failure", failed_results[0]["error"])
        self.assertEqual(failed_results[0]["provider"], "smtp")
        self.assertIsNone(successful_results[0]["error"])
        self.assertEqual(smtp_instance.send_message.call_count, 2)

    def test_uses_smtp_ssl_for_port_465(self):
        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance
        env = {**EMAIL_ENV, "SMTP_PORT": "465"}

        with patch.dict(os.environ, env, clear=True):
            with patch("services.email_service.smtplib.SMTP_SSL", return_value=smtp_context) as smtp_ssl_class:
                send_report_notification_to_parents(self.db, self.report_card.id)

        smtp_ssl_class.assert_called_once_with("smtp.example.test", 465)
        smtp_instance.starttls.assert_not_called()
        smtp_instance.login.assert_called_once_with("smtp-user", "smtp-password")
        smtp_instance.send_message.assert_called_once()

    def test_missing_report_card_raises_value_error(self):
        with patch.dict(os.environ, EMAIL_ENV, clear=True):
            with self.assertRaisesRegex(ValueError, "Report card not found"):
                send_report_notification_to_parents(self.db, uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
