import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Course, ReportCard, ReportCardCourse, Student, Teacher, User
from services.ai_checker import check_report_card_data


class AiCheckerScaleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        teacher_user = User(
            name="Teacher", email="checker@example.test", password_hash="hash", role="teacher"
        )
        self.teacher = Teacher(user=teacher_user, employee_number="T-CHK")
        self.student = Student(
            first_name="Check",
            last_name="Scale",
            grade_level="Grade 12",
            student_number="CHK001",
        )
        # Course has no grade items and no enrollments, so the only warnings that
        # can appear come from the report-course average range check.
        self.course = Course(
            name="Mathematics",
            code="MATH-CHK",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add_all([self.student, self.course])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _report_with_average(self, average: float, scale: str) -> ReportCard:
        report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=average,
            gpa=3.0,
            scale=scale,
            status="approved",
        )
        self.db.add(report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=report_card.id,
                course_id=self.course.id,
                course_name="Mathematics",
                average=average,
                letter_grade="A",
            )
        )
        self.db.commit()
        return report_card

    def test_scale_100_report_with_high_average_does_not_false_fire(self):
        # 88 is valid on /100 but would be out of range on /20.
        report_card = self._report_with_average(88.0, "100")

        warnings = check_report_card_data(self.db, report_card.id)

        types = {warning["warning_type"] for warning in warnings}
        self.assertNotIn("report_course_average_out_of_range", types)

    def test_scale_20_report_with_out_of_range_average_fires(self):
        report_card = self._report_with_average(90.0, "20")

        warnings = check_report_card_data(self.db, report_card.id)

        out_of_range = [
            warning
            for warning in warnings
            if warning["warning_type"] == "report_course_average_out_of_range"
        ]
        self.assertEqual(len(out_of_range), 1)
        self.assertIn("0-20", out_of_range[0]["message"])


if __name__ == "__main__":
    unittest.main()
