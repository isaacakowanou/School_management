import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Course, CourseResult, ReportCard, ReportCardCourse, Student, Teacher, User
from services.report_builder import (
    build_report_card_data,
    build_report_card_data_from_report_card,
)


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


class BuildFromReportCardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.teacher_user = User(
            name="Teacher One", email="from-rc@example.test", password_hash="hash", role="teacher"
        )
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-200")
        self.student = Student(
            first_name="Amina",
            last_name="Diallo",
            grade_level="Grade 12",
            student_number="STU010",
        )
        self.math = Course(
            name="Mathematics",
            code="MATH-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add_all([self.student, self.math])
        self.db.flush()

        # overall_average is intentionally inconsistent with the course average to
        # prove reconstruction reads stored values rather than recomputing them.
        self.report_card = ReportCard(
            student=self.student,
            term="Fall",
            school_year="2026-2027",
            overall_average=88.88,
            gpa=3.5,
            status="approved",
            ai_summary="Strong term.",
        )
        self.db.add(self.report_card)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card_id=self.report_card.id,
                course_id=self.math.id,
                course_name="Mathematics",
                average=91.7,
                letter_grade="A",
            )
        )
        self.db.commit()
        self.db.refresh(self.report_card)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_uses_stored_report_card_values(self):
        data = build_report_card_data_from_report_card(self.db, self.report_card)

        self.assertEqual(data["term"], "Fall")
        self.assertEqual(data["school_year"], "2026-2027")
        self.assertEqual(data["overall_average"], 88.88)
        self.assertEqual(data["gpa"], 3.5)
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["ai_summary"], "Strong term.")
        self.assertIsNotNone(data["generated_date"])

    def test_includes_student_info(self):
        data = build_report_card_data_from_report_card(self.db, self.report_card)

        self.assertEqual(data["student"]["first_name"], "Amina")
        self.assertEqual(data["student"]["last_name"], "Diallo")
        self.assertEqual(data["student"]["student_number"], "STU010")
        self.assertEqual(data["student"]["grade_level"], "Grade 12")

    def test_includes_course_rows_and_resolves_course_code(self):
        data = build_report_card_data_from_report_card(self.db, self.report_card)

        self.assertEqual(len(data["courses"]), 1)
        course = data["courses"][0]
        self.assertEqual(course["course_name"], "Mathematics")
        self.assertEqual(course["course_code"], "MATH-12")
        self.assertEqual(course["average"], 91.7)
        self.assertEqual(course["letter_grade"], "A")

    def test_missing_course_falls_back_to_na(self):
        self.db.add(
            ReportCardCourse(
                report_card_id=self.report_card.id,
                course_id=uuid.uuid4(),
                course_name="Ghost Course",
                average=70.0,
                letter_grade="C",
            )
        )
        self.db.commit()
        self.db.refresh(self.report_card)

        data = build_report_card_data_from_report_card(self.db, self.report_card)
        ghost = next(course for course in data["courses"] if course["course_name"] == "Ghost Course")
        self.assertEqual(ghost["course_code"], "N/A")

    def test_does_not_recompute_from_course_results(self):
        # No CourseResult rows exist; build_report_card_data would raise. The
        # reconstruction path must rely solely on the stored snapshot.
        data = build_report_card_data_from_report_card(self.db, self.report_card)

        self.assertEqual(data["overall_average"], 88.88)
        self.assertEqual(data["courses"][0]["average"], 91.7)


if __name__ == "__main__":
    unittest.main()
