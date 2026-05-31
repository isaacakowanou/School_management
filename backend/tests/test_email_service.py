import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Parent, ReportCard, Student, StudentParent, User
from services.email_service import send_report_notification_to_parents


EMAIL_ENV = {
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "smtp-user",
    "SMTP_PASSWORD": "smtp-password",
    "SMTP_FROM_EMAIL": "school@example.test",
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

    def test_sends_email_to_linked_parent_and_returns_results(self):
        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance

        with patch.dict(os.environ, EMAIL_ENV, clear=False):
            with patch("services.email_service.smtplib.SMTP", return_value=smtp_context) as smtp_class:
                results = send_report_notification_to_parents(self.db, self.report_card.id)

        self.assertEqual(results, [{"email": "parent@example.test", "sent": True}])
        smtp_class.assert_called_once_with("smtp.example.test", 587)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("smtp-user", "smtp-password")
        smtp_instance.send_message.assert_called_once()

        message = smtp_instance.send_message.call_args.args[0]
        body = message.get_content()
        self.assertEqual(message["To"], "parent@example.test")
        self.assertEqual(message["From"], "school@example.test")
        self.assertIn("Isaac Akowanou", body)
        self.assertIn("Fall", body)
        self.assertIn("2026-2027", body)
        self.assertIn(f"https://portal.example.test/reports/{self.report_card.id}", body)
        self.assertFalse(message.is_multipart())

    def test_uses_smtp_ssl_for_port_465(self):
        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance
        env = {**EMAIL_ENV, "SMTP_PORT": "465"}

        with patch.dict(os.environ, env, clear=False):
            with patch("services.email_service.smtplib.SMTP_SSL", return_value=smtp_context) as smtp_ssl_class:
                send_report_notification_to_parents(self.db, self.report_card.id)

        smtp_ssl_class.assert_called_once_with("smtp.example.test", 465)
        smtp_instance.starttls.assert_not_called()
        smtp_instance.login.assert_called_once_with("smtp-user", "smtp-password")
        smtp_instance.send_message.assert_called_once()

    def test_missing_report_card_raises_value_error(self):
        with patch.dict(os.environ, EMAIL_ENV, clear=False):
            with self.assertRaisesRegex(ValueError, "Report card not found"):
                send_report_notification_to_parents(self.db, uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
