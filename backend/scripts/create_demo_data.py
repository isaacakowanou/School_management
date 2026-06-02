"""Create repeatable local demo data for the School AI backend."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Course,
    CourseResult,
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
from services.grade_calculator import (  # noqa: E402
    calculate_course_average,
    calculate_gpa,
    calculate_overall_average,
    get_letter_grade,
)
from services.pdf_generator import generate_report_card_pdf  # noqa: E402


DEMO_PASSWORD = "dev-password-123"
DEMO_TERM = "Fall"
DEMO_SCHOOL_YEAR = "2026-2027"
DEMO_SUMMARY = (
    "Demo Student performed strongly this term in Demo Mathematics. The report shows a "
    "solid overall average and GPA based on the recorded homework, midterm, and final grades."
)


class DemoStats:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.reused: list[str] = []
        self.updated: list[str] = []

    def create(self, label: str) -> None:
        self.created.append(label)

    def reuse(self, label: str) -> None:
        self.reused.append(label)

    def update(self, label: str) -> None:
        self.updated.append(label)

    def print_summary(self) -> None:
        print("Demo data ready.")
        print(f"Created: {len(self.created)}")
        print(f"Reused: {len(self.reused)}")
        print(f"Updated: {len(self.updated)}")
        if self.created:
            print("Created records:")
            for label in self.created:
                print(f"- {label}")


def get_or_create_user(db: Session, stats: DemoStats, *, name: str, email: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
        )
        db.add(user)
        stats.create(f"user {email}")
        return user

    stats.reuse(f"user {email}")
    if user.name != name or user.role != role:
        user.name = name
        user.role = role
        stats.update(f"user {email}")
    user.password_hash = hash_password(DEMO_PASSWORD)
    return user


def get_or_create_parent(db: Session, stats: DemoStats, *, user: User) -> Parent:
    parent = db.scalar(select(Parent).where(Parent.user == user))
    if parent is None:
        parent = Parent(user=user, phone="555-0199")
        db.add(parent)
        stats.create("parent profile")
        return parent

    stats.reuse("parent profile")
    if parent.phone != "555-0199":
        parent.phone = "555-0199"
        stats.update("parent profile")
    return parent


def get_or_create_teacher(db: Session, stats: DemoStats, *, user: User) -> Teacher:
    teacher = db.scalar(select(Teacher).where(Teacher.employee_number == "DEMO-TCH-001"))
    if teacher is None:
        teacher = Teacher(user=user, employee_number="DEMO-TCH-001")
        db.add(teacher)
        stats.create("teacher profile")
        return teacher

    stats.reuse("teacher profile")
    if teacher.user_id != user.id:
        teacher.user = user
        stats.update("teacher profile")
    return teacher


def get_or_create_student(db: Session, stats: DemoStats) -> Student:
    student = db.scalar(select(Student).where(Student.student_number == "DEMO-STU-001"))
    if student is None:
        student = Student(
            first_name="Demo",
            last_name="Student",
            student_number="DEMO-STU-001",
            grade_level="12",
        )
        db.add(student)
        stats.create("student DEMO-STU-001")
        return student

    stats.reuse("student DEMO-STU-001")
    if (
        student.first_name != "Demo"
        or student.last_name != "Student"
        or student.grade_level != "12"
    ):
        student.first_name = "Demo"
        student.last_name = "Student"
        student.grade_level = "12"
        stats.update("student DEMO-STU-001")
    return student


def get_or_create_student_parent(
    db: Session,
    stats: DemoStats,
    *,
    student: Student,
    parent: Parent,
) -> StudentParent:
    link = db.scalar(
        select(StudentParent).where(
            StudentParent.student == student,
            StudentParent.parent == parent,
        )
    )
    if link is None:
        link = StudentParent(student=student, parent=parent, relationship="Guardian")
        db.add(link)
        stats.create("student-parent link")
        return link

    stats.reuse("student-parent link")
    if link.relationship != "Guardian":
        link.relationship = "Guardian"
        stats.update("student-parent link")
    return link


def get_or_create_course(db: Session, stats: DemoStats, *, teacher: Teacher) -> Course:
    course = db.scalar(select(Course).where(Course.code == "DEMO-MATH-2026"))
    if course is None:
        course = Course(
            name="Demo Mathematics",
            code="DEMO-MATH-2026",
            teacher=teacher,
            grade_level="12",
            term=DEMO_TERM,
            school_year=DEMO_SCHOOL_YEAR,
        )
        db.add(course)
        stats.create("course DEMO-MATH-2026")
        return course

    stats.reuse("course DEMO-MATH-2026")
    if (
        course.name != "Demo Mathematics"
        or course.teacher_id != teacher.id
        or course.grade_level != "12"
        or course.term != DEMO_TERM
        or course.school_year != DEMO_SCHOOL_YEAR
    ):
        course.name = "Demo Mathematics"
        course.teacher = teacher
        course.grade_level = "12"
        course.term = DEMO_TERM
        course.school_year = DEMO_SCHOOL_YEAR
        stats.update("course DEMO-MATH-2026")
    return course


def get_or_create_enrollment(
    db: Session,
    stats: DemoStats,
    *,
    student: Student,
    course: Course,
) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student == student,
            Enrollment.course == course,
        )
    )
    if enrollment is None:
        enrollment = Enrollment(student=student, course=course)
        db.add(enrollment)
        stats.create("enrollment")
        return enrollment

    stats.reuse("enrollment")
    return enrollment


def get_or_create_grade_item(
    db: Session,
    stats: DemoStats,
    *,
    course: Course,
    title: str,
    weight: float,
) -> GradeItem:
    grade_item = db.scalar(
        select(GradeItem).where(
            GradeItem.course == course,
            GradeItem.title == title,
        )
    )
    if grade_item is None:
        grade_item = GradeItem(
            course=course,
            title=title,
            category=title,
            max_score=100,
            weight=weight,
            term=DEMO_TERM,
        )
        db.add(grade_item)
        stats.create(f"grade item {title}")
        return grade_item

    stats.reuse(f"grade item {title}")
    if (
        grade_item.category != title
        or grade_item.max_score != 100
        or grade_item.weight != weight
        or grade_item.term != DEMO_TERM
    ):
        grade_item.category = title
        grade_item.max_score = 100
        grade_item.weight = weight
        grade_item.term = DEMO_TERM
        stats.update(f"grade item {title}")
    return grade_item


def get_or_create_grade(
    db: Session,
    stats: DemoStats,
    *,
    student: Student,
    grade_item: GradeItem,
    score: float,
    teacher: Teacher,
) -> Grade:
    grade = db.scalar(
        select(Grade).where(
            Grade.student == student,
            Grade.grade_item == grade_item,
        )
    )
    if grade is None:
        grade = Grade(
            student=student,
            grade_item=grade_item,
            score=score,
            submitted_by_teacher=teacher,
        )
        db.add(grade)
        stats.create(f"grade {grade_item.title}")
        return grade

    stats.reuse(f"grade {grade_item.title}")
    if grade.score != score or grade.submitted_by_teacher_id != teacher.id:
        grade.score = score
        grade.submitted_by_teacher = teacher
        stats.update(f"grade {grade_item.title}")
    return grade


def get_or_create_course_result(
    db: Session,
    stats: DemoStats,
    *,
    student: Student,
    course: Course,
    average: float,
    letter_grade: str,
) -> CourseResult:
    course_result = db.scalar(
        select(CourseResult).where(
            CourseResult.student == student,
            CourseResult.course == course,
            CourseResult.term == DEMO_TERM,
        )
    )
    now = datetime.now(timezone.utc)
    if course_result is None:
        course_result = CourseResult(
            student=student,
            course=course,
            term=DEMO_TERM,
            average=average,
            letter_grade=letter_grade,
            calculated_at=now,
        )
        db.add(course_result)
        stats.create("course result")
        return course_result

    stats.reuse("course result")
    if course_result.average != average or course_result.letter_grade != letter_grade:
        course_result.average = average
        course_result.letter_grade = letter_grade
        stats.update("course result")
    course_result.calculated_at = now
    return course_result


def build_report_data(
    *,
    student: Student,
    course: Course,
    average: float,
    letter_grade: str,
    overall_average: float,
    gpa: float,
) -> dict:
    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_number": student.student_number,
            "grade_level": student.grade_level,
        },
        "term": DEMO_TERM,
        "school_year": DEMO_SCHOOL_YEAR,
        "courses": [
            {
                "course_id": course.id,
                "course_name": course.name,
                "course_code": course.code,
                "average": average,
                "letter_grade": letter_grade,
            }
        ],
        "overall_average": overall_average,
        "gpa": gpa,
        "ai_summary": DEMO_SUMMARY,
        "status": "approved",
        "generated_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_or_create_report_card(
    db: Session,
    stats: DemoStats,
    *,
    admin_user: User,
    student: Student,
    pdf_path: str,
    overall_average: float,
    gpa: float,
) -> ReportCard:
    report_card = db.scalar(
        select(ReportCard)
        .where(
            ReportCard.student == student,
            ReportCard.term == DEMO_TERM,
            ReportCard.school_year == DEMO_SCHOOL_YEAR,
        )
        .order_by(ReportCard.created_at.desc())
    )
    approved_at = datetime.now(timezone.utc)
    if report_card is None:
        report_card = ReportCard(
            student=student,
            term=DEMO_TERM,
            school_year=DEMO_SCHOOL_YEAR,
            overall_average=overall_average,
            gpa=gpa,
            status="approved",
            ai_summary=DEMO_SUMMARY,
            pdf_url=pdf_path,
            approved_by_admin=admin_user,
            approved_at=approved_at,
            sent_at=None,
        )
        db.add(report_card)
        stats.create("approved report card")
        return report_card

    stats.reuse("approved report card")
    report_card.overall_average = overall_average
    report_card.gpa = gpa
    report_card.status = "approved"
    report_card.ai_summary = DEMO_SUMMARY
    report_card.pdf_url = pdf_path
    report_card.approved_by_admin = admin_user
    report_card.approved_at = approved_at
    report_card.sent_at = None
    stats.update("approved report card")
    return report_card


def get_or_create_report_card_course(
    db: Session,
    stats: DemoStats,
    *,
    report_card: ReportCard,
    course: Course,
    average: float,
    letter_grade: str,
) -> ReportCardCourse:
    report_card_course = db.scalar(
        select(ReportCardCourse).where(
            ReportCardCourse.report_card == report_card,
            ReportCardCourse.course == course,
        )
    )
    if report_card_course is None:
        report_card_course = ReportCardCourse(
            report_card=report_card,
            course=course,
            course_name=course.name,
            average=average,
            letter_grade=letter_grade,
        )
        db.add(report_card_course)
        stats.create("report card course")
        return report_card_course

    stats.reuse("report card course")
    if (
        report_card_course.course_name != course.name
        or report_card_course.average != average
        or report_card_course.letter_grade != letter_grade
    ):
        report_card_course.course_name = course.name
        report_card_course.average = average
        report_card_course.letter_grade = letter_grade
        stats.update("report card course")
    return report_card_course


def create_demo_data() -> None:
    stats = DemoStats()
    db = SessionLocal()
    try:
        admin_user = get_or_create_user(
            db,
            stats,
            name="Demo Admin",
            email="demo-admin@school.test",
            role="admin",
        )
        teacher_user = get_or_create_user(
            db,
            stats,
            name="Demo Teacher",
            email="demo-teacher@school.test",
            role="teacher",
        )
        parent_user = get_or_create_user(
            db,
            stats,
            name="Demo Parent",
            email="demo-parent@school.test",
            role="parent",
        )
        db.flush()

        teacher = get_or_create_teacher(db, stats, user=teacher_user)
        parent = get_or_create_parent(db, stats, user=parent_user)
        student = get_or_create_student(db, stats)
        db.flush()

        get_or_create_student_parent(db, stats, student=student, parent=parent)
        course = get_or_create_course(db, stats, teacher=teacher)
        db.flush()
        get_or_create_enrollment(db, stats, student=student, course=course)
        db.flush()

        grade_items = [
            get_or_create_grade_item(db, stats, course=course, title="Homework", weight=0.30),
            get_or_create_grade_item(db, stats, course=course, title="Midterm", weight=0.30),
            get_or_create_grade_item(db, stats, course=course, title="Final", weight=0.40),
        ]
        db.flush()

        scores_by_title = {"Homework": 95, "Midterm": 88, "Final": 92}
        grades = [
            get_or_create_grade(
                db,
                stats,
                student=student,
                grade_item=grade_item,
                score=scores_by_title[grade_item.title],
                teacher=teacher,
            )
            for grade_item in grade_items
        ]
        db.flush()

        grade_inputs = [
            {
                "score": grade.score,
                "max_score": grade.grade_item.max_score,
                "weight": grade.grade_item.weight,
            }
            for grade in grades
        ]
        course_average = calculate_course_average(grade_inputs)
        letter_grade = get_letter_grade(course_average)
        overall_average = calculate_overall_average([course_average])
        gpa = calculate_gpa([course_average])

        get_or_create_course_result(
            db,
            stats,
            student=student,
            course=course,
            average=course_average,
            letter_grade=letter_grade,
        )
        db.flush()

        report_data = build_report_data(
            student=student,
            course=course,
            average=course_average,
            letter_grade=letter_grade,
            overall_average=overall_average,
            gpa=gpa,
        )
        pdf_path = generate_report_card_pdf(report_data)

        report_card = get_or_create_report_card(
            db,
            stats,
            admin_user=admin_user,
            student=student,
            pdf_path=pdf_path,
            overall_average=overall_average,
            gpa=gpa,
        )
        db.flush()
        get_or_create_report_card_course(
            db,
            stats,
            report_card=report_card,
            course=course,
            average=course_average,
            letter_grade=letter_grade,
        )

        db.commit()

        stats.print_summary()
        print(f"Demo parent login: demo-parent@school.test / {DEMO_PASSWORD}")
        print(f"Demo admin login: demo-admin@school.test / {DEMO_PASSWORD}")
        print(f"Demo teacher login: demo-teacher@school.test / {DEMO_PASSWORD}")
        print(f"Course average: {course_average:.2f}")
        print(f"Letter grade: {letter_grade}")
        print(f"Overall average: {overall_average:.2f}")
        print(f"GPA: {gpa:.2f}")
        print(f"Report status: {report_card.status}")
        print(f"PDF: {pdf_path}")
    finally:
        db.close()


if __name__ == "__main__":
    create_demo_data()
