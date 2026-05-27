import tempfile
import unittest
from pathlib import Path

from services.pdf_generator import generate_report_card_pdf


def sample_report_data(include_summary=False):
    report_data = {
        "student": {
            "id": "student-1",
            "first_name": "Isaac",
            "last_name": "Akowanou",
            "student_number": "STU001",
            "grade_level": "Grade 12",
        },
        "term": "Fall",
        "school_year": "2026-2027",
        "courses": [
            {
                "course_id": "course-1",
                "course_name": "Mathematics",
                "course_code": "MATH-12",
                "average": 91.7,
                "letter_grade": "A",
            }
        ],
        "overall_average": 91.7,
        "gpa": 4.0,
    }
    if include_summary:
        report_data["ai_summary"] = "Isaac performed strongly this term."
    return report_data


class PdfGeneratorTests(unittest.TestCase):
    def test_generate_report_card_pdf_creates_non_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = generate_report_card_pdf(sample_report_data(include_summary=True), output_dir=temp_dir)
            path = Path(pdf_path)

            self.assertTrue(path.exists())
            self.assertEqual(path.name, "STU001_Fall_2026-2027.pdf")
            self.assertGreater(path.stat().st_size, 0)

    def test_generate_report_card_pdf_works_without_ai_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = generate_report_card_pdf(sample_report_data(), output_dir=temp_dir)
            path = Path(pdf_path)

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
