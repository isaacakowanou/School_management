import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from models import Base, Course, CourseResult, ReportCard, ReportCardCourse, Student, Teacher, User
from services.report_builder import (
    build_report_card_data,
    build_report_card_data_from_report_card,
    get_report_card_staleness,
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

    def test_scale_100_course_result_is_normalized_to_20(self):
        # A historical /100 course result must be scaled down to /20 before it is
        # used in the report's averages.
        legacy_student = Student(
            first_name="Legacy",
            last_name="Scale",
            grade_level="Grade 12",
            student_number="STU100",
        )
        history = Course(
            name="History",
            code="HIST-100",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall 2026",
            school_year="2026-2027",
        )
        self.db.add_all([legacy_student, history])
        self.db.flush()
        self.db.add(
            CourseResult(
                student=legacy_student,
                course=history,
                term="Fall 2026",
                average=90.0,
                letter_grade="A",
                scale="100",
            )
        )
        self.db.commit()

        report_data = build_report_card_data(
            self.db,
            legacy_student.id,
            term="Fall 2026",
            school_year="2026-2027",
        )

        self.assertEqual(report_data["courses"][0]["average"], 18.0)
        self.assertEqual(report_data["overall_average"], 18.0)
        self.assertEqual(report_data["scale"], "20")

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


class ReportCardStalenessTests(unittest.TestCase):
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
            email="stale-teacher@example.test",
            password_hash="hash",
            role="teacher",
        )
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-STALE")
        self.student = Student(
            first_name="Stale",
            last_name="Student",
            grade_level="Grade 12",
            student_number="STU-STALE",
        )
        self.math = Course(
            name="Mathematics",
            code="MATH-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.science = Course(
            name="Science",
            code="SCI-12",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add_all([self.student, self.math, self.science])
        self.db.flush()

        self.math_result = CourseResult(
            student=self.student,
            course=self.math,
            term="Fall",
            average=95.0,
            letter_grade="A",
        )
        self.science_result = CourseResult(
            student=self.student,
            course=self.science,
            term="Fall",
            average=85.0,
            letter_grade="B",
        )
        self.db.add_all([self.math_result, self.science_result])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_matching_report_card(self) -> ReportCard:
        report_data = build_report_card_data(
            self.db,
            self.student.id,
            term="Fall",
            school_year="2026-2027",
        )
        report_card = ReportCard(
            student_id=self.student.id,
            term="Fall",
            school_year="2026-2027",
            overall_average=report_data["overall_average"],
            gpa=report_data["gpa"],
            status="approved",
        )
        self.db.add(report_card)
        self.db.flush()
        for course in report_data["courses"]:
            self.db.add(
                ReportCardCourse(
                    report_card_id=report_card.id,
                    course_id=course["course_id"],
                    course_name=course["course_name"],
                    average=course["average"],
                    letter_grade=course["letter_grade"],
                )
            )
        self.db.commit()
        self.db.refresh(report_card)
        return report_card

    def test_stale_false_when_snapshot_matches_current_results(self):
        report_card = self._create_matching_report_card()

        staleness = get_report_card_staleness(self.db, report_card)

        self.assertFalse(staleness.is_stale)
        self.assertEqual(staleness.reason, "Report snapshot matches current course results.")
        self.assertEqual(staleness.snapshot_overall_average, staleness.current_overall_average)
        self.assertEqual(staleness.snapshot_gpa, staleness.current_gpa)

    def test_stale_true_when_course_result_changes(self):
        report_card = self._create_matching_report_card()
        self.math_result.average = 75.0
        self.math_result.letter_grade = "C"
        self.db.commit()

        staleness = get_report_card_staleness(self.db, report_card)

        self.assertTrue(staleness.is_stale)
        self.assertIn("overall_average changed", staleness.reason)
        self.assertIn("course average changed", staleness.reason)
        self.assertIn("letter grade changed", staleness.reason)
        self.assertNotEqual(staleness.snapshot_overall_average, staleness.current_overall_average)

    def test_stale_true_when_course_set_differs(self):
        report_card = self._create_matching_report_card()
        snapshot_course = self.db.scalar(
            select(ReportCardCourse).where(ReportCardCourse.report_card_id == report_card.id)
        )
        self.db.delete(snapshot_course)
        self.db.commit()
        self.db.refresh(report_card)

        staleness = get_report_card_staleness(self.db, report_card)

        self.assertTrue(staleness.is_stale)
        self.assertIn("course set changed", staleness.reason)

    def test_stale_true_when_current_results_are_missing(self):
        report_card = self._create_matching_report_card()
        self.db.delete(self.math_result)
        self.db.delete(self.science_result)
        self.db.commit()

        staleness = get_report_card_staleness(self.db, report_card)

        self.assertTrue(staleness.is_stale)
        self.assertIn("Current report data could not be built", staleness.reason)
        self.assertIsNone(staleness.current_overall_average)
        self.assertIsNone(staleness.current_gpa)


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
