import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, ReportCard, ReportCardCourse, Student
from routes.ai import generate_summary_for_report
from services.ai_summary import generate_report_summary


def sample_report_data():
    return {
        "student": {
            "first_name": "Isaac",
            "last_name": "Akowanou",
            "grade_level": "Grade 12",
        },
        "term": "Fall",
        "school_year": "2026-2027",
        "courses": [
            {
                "course_name": "Mathematics",
                "average": 91.7,
                "letter_grade": "A",
            },
            {
                "course_name": "Computer Science",
                "average": 96.5,
                "letter_grade": "A",
            },
        ],
        "overall_average": 94.1,
        "gpa": 4.0,
    }


class FakeMessage:
    content = "Isaac performed strongly this term in Mathematics and Computer Science."


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class AISummaryServiceTests(unittest.TestCase):
    def test_generate_report_summary_uses_report_data_and_returns_text(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = FakeResponse()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}):
            with patch("services.ai_summary._create_openai_client", return_value=fake_client):
                summary = generate_report_summary(sample_report_data())

        self.assertEqual(summary, "Isaac performed strongly this term in Mathematics and Computer Science.")
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "test-model")
        self.assertEqual(call_kwargs["temperature"], 0.7)

        messages = call_kwargs["messages"]
        prompt_text = messages[1]["content"]
        self.assertIn("Isaac Akowanou", prompt_text)
        self.assertIn("Grade 12", prompt_text)
        self.assertIn("Fall", prompt_text)
        self.assertIn("2026-2027", prompt_text)
        self.assertIn("Mathematics: 91.70, A", prompt_text)
        self.assertIn("Computer Science: 96.50, A", prompt_text)
        self.assertIn("Overall average: 94.10", prompt_text)
        self.assertIn("GPA: 4.00", prompt_text)
        self.assertNotIn("teacher", prompt_text.lower())
        self.assertNotIn("attendance record", prompt_text.lower())

    def test_missing_openai_api_key_raises_value_error(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
                generate_report_summary(sample_report_data())


class AISummaryRouteTests(unittest.TestCase):
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
        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=94.1,
            gpa=4.0,
            status="draft",
        )
        self.db.add(self.report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card=self.report_card,
                course_id=uuid.uuid4(),
                course_name="Mathematics",
                average=91.7,
                letter_grade="A",
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_generate_summary_route_saves_ai_summary(self):
        expected_summary = "Isaac performed strongly this term in Mathematics."
        with patch("routes.ai.generate_report_summary", return_value=expected_summary):
            response = generate_summary_for_report(self.report_card.id, db=self.db, _=object())

        self.db.refresh(self.report_card)
        self.assertEqual(response.report_card_id, self.report_card.id)
        self.assertEqual(response.ai_summary, expected_summary)
        self.assertEqual(self.report_card.ai_summary, expected_summary)

    def test_generate_summary_route_missing_report_returns_404(self):
        with self.assertRaises(HTTPException) as exc:
            generate_summary_for_report(uuid.uuid4(), db=self.db, _=object())

        self.assertEqual(exc.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
