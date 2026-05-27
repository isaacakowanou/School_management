import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Course, CourseResult, Student, Teacher, User
from services.report_builder import build_report_card_data


class ReportBuilderTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.teacher_user = User(
            name="Teacher One",
            email="teacher@example.test",
            password_hash="hash",
            role="teacher",
        )
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-001")
        self.student = Student(
            first_name="Isaac",
            last_name="Akowanou",
            grade_level="Grade 12",
            student_number="STU001",
        )
        self.math = Course(
            name="Mathematics",
            code="MATH-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall 2026",
            school_year="2026-2027",
        )
        self.cs = Course(
            name="Computer Science",
            code="CS-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall 2026",
            school_year="2026-2027",
        )
        self.old_course = Course(
            name="Old Mathematics",
            code="MATH-OLD",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall 2026",
            school_year="2025-2026",
        )
        self.db.add_all([self.student, self.math, self.cs, self.old_course])
        self.db.flush()

        self.db.add_all(
            [
                CourseResult(
                    student=self.student,
                    course=self.math,
                    term="Fall 2026",
                    average=91.7,
                    letter_grade="A",
                ),
                CourseResult(
                    student=self.student,
                    course=self.cs,
                    term="Fall 2026",
                    average=96.5,
                    letter_grade="A",
                ),
                CourseResult(
                    student=self.student,
                    course=self.old_course,
                    term="Fall 2026",
                    average=70,
                    letter_grade="C",
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_build_report_card_data_returns_student_info_and_courses(self):
        report_data = build_report_card_data(
            self.db,
            self.student.id,
            term="Fall 2026",
            school_year="2026-2027",
        )

        self.assertEqual(report_data["student"]["id"], self.student.id)
        self.assertEqual(report_data["student"]["first_name"], "Isaac")
        self.assertEqual(report_data["student"]["last_name"], "Akowanou")
        self.assertEqual(report_data["student"]["student_number"], "STU001")
        self.assertEqual(report_data["student"]["grade_level"], "Grade 12")
        self.assertEqual(report_data["term"], "Fall 2026")
        self.assertEqual(report_data["school_year"], "2026-2027")

        courses_by_code = {course["course_code"]: course for course in report_data["courses"]}
        self.assertEqual(set(courses_by_code), {"CS-12", "MATH-12"})
        self.assertEqual(courses_by_code["MATH-12"]["course_id"], self.math.id)
        self.assertEqual(courses_by_code["MATH-12"]["course_name"], "Mathematics")
        self.assertEqual(courses_by_code["MATH-12"]["average"], 91.7)
        self.assertEqual(courses_by_code["MATH-12"]["letter_grade"], "A")

    def test_overall_average_and_gpa_use_calculator_outputs(self):
        report_data = build_report_card_data(
            self.db,
            self.student.id,
            term="Fall 2026",
            school_year="2026-2027",
        )

        self.assertEqual(report_data["overall_average"], 94.1)
        self.assertEqual(report_data["gpa"], 4.0)

    def test_missing_student_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "Student not found"):
            build_report_card_data(
                self.db,
                uuid.uuid4(),
                term="Fall 2026",
                school_year="2026-2027",
            )

    def test_student_with_no_course_results_raises_value_error(self):
        student_without_results = Student(
            first_name="No",
            last_name="Results",
            grade_level="Grade 12",
            student_number="STU999",
        )
        self.db.add(student_without_results)
        self.db.commit()

        with self.assertRaisesRegex(ValueError, "Student has no course results"):
            build_report_card_data(
                self.db,
                student_without_results.id,
                term="Fall 2026",
                school_year="2026-2027",
            )


if __name__ == "__main__":
    unittest.main()
