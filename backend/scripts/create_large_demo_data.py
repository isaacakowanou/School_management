"""Create repeatable large demo/stress data for the School AI backend.

This script is intentionally separate from create_demo_data.py. It uses STRESS-*
natural keys so it can be rerun without duplicating records and without touching
the original demo-admin/demo-teacher/demo-parent accounts.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from audit import create_audit_log  # noqa: E402
from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
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
from services.grade_calculator import calculate_course_average, get_letter_grade  # noqa: E402
from services.report_builder import build_report_card_data  # noqa: E402


STRESS_PASSWORD = "stress-password-123"
STRESS_TERM = "Fall"
STRESS_SCHOOL_YEAR = "2026-2027"

STUDENT_COUNT = 100
PARENT_COUNT = 20
TEACHER_COUNT = 8
REPORT_COUNT = STUDENT_COUNT
STUDENTS_PER_COURSE = 25

COURSE_DEFS = [
    ("STRESS-MATH-001", "Stress Algebra I", "Mathematics"),
    ("STRESS-SCI-001", "Stress Biology", "Science"),
    ("STRESS-ENG-001", "Stress Literature", "English"),
    ("STRESS-HIST-001", "Stress World History", "History"),
    ("STRESS-ART-001", "Stress Visual Arts", "Arts"),
    ("STRESS-TECH-001", "Stress Computer Science", "Technology"),
    ("STRESS-MATH-002", "Stress Geometry", "Mathematics"),
    ("STRESS-SCI-002", "Stress Chemistry", "Science"),
    ("STRESS-ENG-002", "Stress Writing", "English"),
    ("STRESS-HIST-002", "Stress Civics", "History"),
    ("STRESS-BUS-001", "Stress Economics", "Business"),
    ("STRESS-PE-001", "Stress Health", "Physical Education"),
]

GRADE_ITEM_PATTERNS = [
    [
        ("Homework", 0.30),
        ("Project", 0.30),
        ("Final", 0.40),
    ],
    [
        ("Homework", 0.20),
        ("Quiz", 0.20),
        ("Project", 0.25),
        ("Final", 0.35),
    ],
    [
        ("Homework", 0.15),
        ("Quiz", 0.15),
        ("Lab", 0.20),
        ("Midterm", 0.20),
        ("Final", 0.30),
    ],
]


class StressStats:
    def __init__(self) -> None:
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)

    def create(self, category: str) -> None:
        self.counts[category]["created"] += 1

    def reuse(self, category: str) -> None:
        self.counts[category]["reused"] += 1

    def update(self, category: str) -> None:
        self.counts[category]["updated"] += 1

    def print_summary(self) -> None:
        categories = [
            "users",
            "students",
            "parents",
            "teachers",
            "student_parent_links",
            "courses",
            "grade_items",
            "enrollments",
            "grades",
            "course_results",
            "reports",
            "report_courses",
            "audit_logs",
        ]
        print("Large stress demo data ready.")
        for category in categories:
            counts = self.counts[category]
            print(
                f"{category}: "
                f"created={counts['created']} "
                f"reused={counts['reused']} "
                f"updated={counts['updated']}"
            )


def changed(obj, **values) -> bool:
    did_change = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            did_change = True
    return did_change


def numbers_differ(left: float | None, right: float | None, tolerance: float = 0.005) -> bool:
    if left is None or right is None:
        return left is not None or right is not None
    return abs(float(left) - float(right)) > tolerance


def timestamp_seconds(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


def approved_after_course_results(latest_calculated_at: datetime | None) -> datetime:
    if latest_calculated_at is None:
        return datetime.now(timezone.utc)
    return latest_calculated_at + timedelta(seconds=1)


def approval_needs_refresh(approved_at: datetime | None, latest_calculated_at: datetime | None) -> bool:
    if approved_at is None:
        return True
    latest_seconds = timestamp_seconds(latest_calculated_at)
    approved_seconds = timestamp_seconds(approved_at)
    return latest_seconds is not None and approved_seconds is not None and approved_seconds <= latest_seconds


def padded(index: int) -> str:
    return f"{index:03d}"


def get_or_create_user(db: Session, stats: StressStats, *, name: str, email: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name, email=email, password_hash=hash_password(STRESS_PASSWORD), role=role)
        db.add(user)
        stats.create("users")
        return user

    stats.reuse("users")
    if changed(user, name=name, role=role):
        stats.update("users")
    return user


def get_or_create_parent(db: Session, stats: StressStats, *, user: User, index: int) -> Parent:
    phone = f"555-20{index:02d}"
    parent = db.scalar(select(Parent).where(Parent.user_id == user.id))
    if parent is None:
        parent = Parent(user=user, phone=phone)
        db.add(parent)
        stats.create("parents")
        return parent

    stats.reuse("parents")
    if changed(parent, phone=phone):
        stats.update("parents")
    return parent


def get_or_create_teacher(db: Session, stats: StressStats, *, user: User, index: int) -> Teacher:
    employee_number = f"STRESS-TCH-{padded(index)}"
    teacher = db.scalar(select(Teacher).where(Teacher.employee_number == employee_number))
    if teacher is None:
        teacher = Teacher(user=user, employee_number=employee_number)
        db.add(teacher)
        stats.create("teachers")
        return teacher

    stats.reuse("teachers")
    if teacher.user_id != user.id:
        teacher.user = user
        stats.update("teachers")
    return teacher


def get_or_create_student(db: Session, stats: StressStats, *, index: int) -> Student:
    student_number = f"STRESS-STU-{padded(index)}"
    first_name = "Stress"
    last_name = f"Student {padded(index)}"
    grade_level = str(9 + ((index - 1) % 4))

    student = db.scalar(select(Student).where(Student.student_number == student_number))
    if student is None:
        student = Student(
            first_name=first_name,
            last_name=last_name,
            student_number=student_number,
            grade_level=grade_level,
        )
        db.add(student)
        stats.create("students")
        return student

    stats.reuse("students")
    if changed(student, first_name=first_name, last_name=last_name, grade_level=grade_level):
        stats.update("students")
    return student


def get_or_create_student_parent(
    db: Session,
    stats: StressStats,
    *,
    student: Student,
    parent: Parent,
) -> StudentParent:
    link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student.id,
            StudentParent.parent_id == parent.id,
        )
    )
    if link is None:
        link = StudentParent(student=student, parent=parent, relationship="Guardian")
        db.add(link)
        stats.create("student_parent_links")
        return link

    stats.reuse("student_parent_links")
    if changed(link, relationship="Guardian"):
        stats.update("student_parent_links")
    return link


def get_or_create_course(
    db: Session,
    stats: StressStats,
    *,
    code: str,
    name: str,
    teacher: Teacher,
) -> Course:
    course = db.scalar(select(Course).where(Course.code == code))
    if course is None:
        course = Course(
            name=name,
            code=code,
            teacher=teacher,
            grade_level="10",
            term=STRESS_TERM,
            school_year=STRESS_SCHOOL_YEAR,
        )
        db.add(course)
        stats.create("courses")
        return course

    stats.reuse("courses")
    did_change = changed(
        course,
        name=name,
        grade_level="10",
        term=STRESS_TERM,
        school_year=STRESS_SCHOOL_YEAR,
    )
    if course.teacher_id != teacher.id:
        course.teacher = teacher
        did_change = True
    if did_change:
        stats.update("courses")
    return course


def grade_item_specs(course_index: int) -> list[tuple[str, float]]:
    return GRADE_ITEM_PATTERNS[(course_index - 1) % len(GRADE_ITEM_PATTERNS)]


def get_or_create_grade_item(
    db: Session,
    stats: StressStats,
    *,
    course: Course,
    title: str,
    weight: float,
) -> GradeItem:
    grade_item = db.scalar(
        select(GradeItem).where(
            GradeItem.course_id == course.id,
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
            term=STRESS_TERM,
        )
        db.add(grade_item)
        stats.create("grade_items")
        return grade_item

    stats.reuse("grade_items")
    if changed(grade_item, category=title, max_score=100, weight=weight, term=STRESS_TERM, due_date=None):
        stats.update("grade_items")
    return grade_item


def students_for_course(course_index: int, students: list[Student]) -> list[Student]:
    start = (course_index - 1) * 8
    return [students[(start + offset) % len(students)] for offset in range(STUDENTS_PER_COURSE)]


def get_or_create_enrollment(
    db: Session,
    stats: StressStats,
    *,
    student: Student,
    course: Course,
) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.course_id == course.id,
        )
    )
    if enrollment is None:
        enrollment = Enrollment(student=student, course=course)
        db.add(enrollment)
        stats.create("enrollments")
        return enrollment

    stats.reuse("enrollments")
    return enrollment


def score_for(student_index: int, course_index: int, grade_item_index: int) -> float:
    return float(65 + ((student_index * 7 + course_index * 11 + grade_item_index * 13) % 36))


def get_or_create_grade(
    db: Session,
    stats: StressStats,
    *,
    student: Student,
    grade_item: GradeItem,
    teacher: Teacher,
    score: float,
) -> Grade:
    grade = db.scalar(
        select(Grade).where(
            Grade.student_id == student.id,
            Grade.grade_item_id == grade_item.id,
        )
    )
    if grade is None:
        grade = Grade(student=student, grade_item=grade_item, submitted_by_teacher=teacher, score=score)
        db.add(grade)
        stats.create("grades")
        return grade

    stats.reuse("grades")
    did_change = False
    if numbers_differ(grade.score, score):
        grade.score = score
        did_change = True
    if grade.submitted_by_teacher_id != teacher.id:
        grade.submitted_by_teacher = teacher
        did_change = True
    if did_change:
        stats.update("grades")
    return grade


def get_or_create_course_result(
    db: Session,
    stats: StressStats,
    *,
    student: Student,
    course: Course,
    average: float,
    letter_grade: str,
) -> CourseResult:
    course_result = db.scalar(
        select(CourseResult).where(
            CourseResult.student_id == student.id,
            CourseResult.course_id == course.id,
            CourseResult.term == STRESS_TERM,
        )
    )
    if course_result is None:
        course_result = CourseResult(
            student=student,
            course=course,
            term=STRESS_TERM,
            average=average,
            letter_grade=letter_grade,
            calculated_at=datetime.now(timezone.utc),
        )
        db.add(course_result)
        stats.create("course_results")
        return course_result

    stats.reuse("course_results")
    did_change = False
    if numbers_differ(course_result.average, average):
        course_result.average = average
        did_change = True
    if course_result.letter_grade != letter_grade:
        course_result.letter_grade = letter_grade
        did_change = True
    if did_change:
        course_result.calculated_at = datetime.now(timezone.utc)
        stats.update("course_results")
    return course_result


def stress_summary_for(student: Student, report_data: dict) -> str:
    return (
        f"{student.first_name} {student.last_name} has a stress-demo report with "
        f"{len(report_data['courses'])} course result rows for load testing. "
        "This summary is deterministic demo text and was not generated by OpenAI."
    )


def latest_report_course_result_time(db: Session, *, student: Student) -> datetime | None:
    return db.scalar(
        select(CourseResult.calculated_at)
        .join(Course, CourseResult.course_id == Course.id)
        .where(
            CourseResult.student_id == student.id,
            CourseResult.term == STRESS_TERM,
            Course.school_year == STRESS_SCHOOL_YEAR,
        )
        .order_by(CourseResult.calculated_at.desc())
        .limit(1)
    )


def get_or_create_report_card(
    db: Session,
    stats: StressStats,
    *,
    admin_user: User,
    student: Student,
    report_data: dict,
) -> ReportCard:
    summary = stress_summary_for(student, report_data)
    latest_calculated_at = latest_report_course_result_time(db, student=student)
    target_approved_at = approved_after_course_results(latest_calculated_at)
    report_card = db.scalar(
        select(ReportCard)
        .where(
            ReportCard.student_id == student.id,
            ReportCard.term == STRESS_TERM,
            ReportCard.school_year == STRESS_SCHOOL_YEAR,
        )
        .order_by(ReportCard.created_at.desc())
    )
    if report_card is None:
        report_card = ReportCard(
            student=student,
            term=STRESS_TERM,
            school_year=STRESS_SCHOOL_YEAR,
            overall_average=report_data["overall_average"],
            gpa=report_data["gpa"],
            status="approved",
            ai_summary=summary,
            pdf_url=None,
            approved_by_admin=admin_user,
            approved_at=target_approved_at,
            sent_at=None,
        )
        db.add(report_card)
        stats.create("reports")
        return report_card

    stats.reuse("reports")
    did_change = False
    if numbers_differ(report_card.overall_average, report_data["overall_average"]):
        report_card.overall_average = report_data["overall_average"]
        did_change = True
    if numbers_differ(report_card.gpa, report_data["gpa"]):
        report_card.gpa = report_data["gpa"]
        did_change = True
    if report_card.status != "approved":
        report_card.status = "approved"
        report_card.approved_at = target_approved_at
        did_change = True
    elif approval_needs_refresh(report_card.approved_at, latest_calculated_at):
        report_card.approved_at = target_approved_at
        did_change = True
    if report_card.ai_summary != summary:
        report_card.ai_summary = summary
        did_change = True
    if report_card.pdf_url is not None:
        report_card.pdf_url = None
        did_change = True
    if report_card.approved_by_admin_id != admin_user.id:
        report_card.approved_by_admin = admin_user
        if approval_needs_refresh(report_card.approved_at, latest_calculated_at):
            report_card.approved_at = target_approved_at
        did_change = True
    if report_card.sent_at is not None:
        report_card.sent_at = None
        did_change = True
    if did_change:
        stats.update("reports")
    return report_card


def get_or_create_report_card_course(
    db: Session,
    stats: StressStats,
    *,
    report_card: ReportCard,
    course_data: dict,
) -> ReportCardCourse:
    report_card_course = db.scalar(
        select(ReportCardCourse).where(
            ReportCardCourse.report_card_id == report_card.id,
            ReportCardCourse.course_id == course_data["course_id"],
        )
    )
    if report_card_course is None:
        report_card_course = ReportCardCourse(
            report_card=report_card,
            course_id=course_data["course_id"],
            course_name=course_data["course_name"],
            average=course_data["average"],
            letter_grade=course_data["letter_grade"],
        )
        db.add(report_card_course)
        stats.create("report_courses")
        return report_card_course

    stats.reuse("report_courses")
    did_change = changed(report_card_course, course_name=course_data["course_name"])
    if numbers_differ(report_card_course.average, course_data["average"]):
        report_card_course.average = course_data["average"]
        did_change = True
    if report_card_course.letter_grade != course_data["letter_grade"]:
        report_card_course.letter_grade = course_data["letter_grade"]
        did_change = True
    if did_change:
        stats.update("report_courses")
    return report_card_course


def get_or_create_audit_log(
    db: Session,
    stats: StressStats,
    *,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: dict,
) -> AuditLog:
    audit_log = db.scalar(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
    )
    if audit_log is not None:
        stats.reuse("audit_logs")
        return audit_log

    audit_log = create_audit_log(
        db=db,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        new_value=new_value,
    )
    stats.create("audit_logs")
    return audit_log


def create_large_demo_data() -> None:
    stats = StressStats()
    db = SessionLocal()
    try:
        admin_user = get_or_create_user(
            db,
            stats,
            name="Stress Admin",
            email="stress-admin@school.test",
            role="admin",
        )
        parent_users = [
            get_or_create_user(
                db,
                stats,
                name=f"Stress Parent {padded(index)}",
                email=f"stress-parent-{padded(index)}@school.test",
                role="parent",
            )
            for index in range(1, PARENT_COUNT + 1)
        ]
        teacher_users = [
            get_or_create_user(
                db,
                stats,
                name=f"Stress Teacher {padded(index)}",
                email=f"stress-teacher-{padded(index)}@school.test",
                role="teacher",
            )
            for index in range(1, TEACHER_COUNT + 1)
        ]
        db.flush()

        parents = [
            get_or_create_parent(db, stats, user=user, index=index)
            for index, user in enumerate(parent_users, start=1)
        ]
        teachers = [
            get_or_create_teacher(db, stats, user=user, index=index)
            for index, user in enumerate(teacher_users, start=1)
        ]
        students = [
            get_or_create_student(db, stats, index=index)
            for index in range(1, STUDENT_COUNT + 1)
        ]
        db.flush()

        for index, student in enumerate(students, start=1):
            parent = parents[(index - 1) % len(parents)]
            get_or_create_student_parent(db, stats, student=student, parent=parent)
        db.flush()

        courses: list[Course] = []
        for index, (code, name, _) in enumerate(COURSE_DEFS, start=1):
            teacher = teachers[(index - 1) % len(teachers)]
            courses.append(get_or_create_course(db, stats, code=code, name=name, teacher=teacher))
        db.flush()

        grade_items_by_course: dict[str, list[GradeItem]] = {}
        for course_index, course in enumerate(courses, start=1):
            grade_items_by_course[course.code] = [
                get_or_create_grade_item(db, stats, course=course, title=title, weight=weight)
                for title, weight in grade_item_specs(course_index)
            ]
        db.flush()

        enrolled_students_by_course: dict[str, list[Student]] = {}
        for course_index, course in enumerate(courses, start=1):
            enrolled_students = students_for_course(course_index, students)
            enrolled_students_by_course[course.code] = enrolled_students
            for student in enrolled_students:
                get_or_create_enrollment(db, stats, student=student, course=course)
        db.flush()

        course_results: list[CourseResult] = []
        for course_index, course in enumerate(courses, start=1):
            grade_items = grade_items_by_course[course.code]
            for student in enrolled_students_by_course[course.code]:
                student_index = int(student.student_number.rsplit("-", 1)[1])
                for grade_item_index, grade_item in enumerate(grade_items, start=1):
                    get_or_create_grade(
                        db,
                        stats,
                        student=student,
                        grade_item=grade_item,
                        teacher=course.teacher,
                        score=score_for(student_index, course_index, grade_item_index),
                    )

                grade_inputs = [
                    {
                        "score": score_for(student_index, course_index, grade_item_index),
                        "max_score": grade_item.max_score,
                        "weight": grade_item.weight,
                    }
                    for grade_item_index, grade_item in enumerate(grade_items, start=1)
                ]
                average = calculate_course_average(grade_inputs)
                letter_grade = get_letter_grade(average)
                course_results.append(
                    get_or_create_course_result(
                        db,
                        stats,
                        student=student,
                        course=course,
                        average=average,
                        letter_grade=letter_grade,
                    )
                )
        db.flush()

        report_cards: list[ReportCard] = []
        for student in students[:REPORT_COUNT]:
            report_data = build_report_card_data(db, student.id, STRESS_TERM, STRESS_SCHOOL_YEAR)
            report_card = get_or_create_report_card(
                db,
                stats,
                admin_user=admin_user,
                student=student,
                report_data=report_data,
            )
            db.flush()
            for course_data in report_data["courses"]:
                get_or_create_report_card_course(
                    db,
                    stats,
                    report_card=report_card,
                    course_data=course_data,
                )
            report_cards.append(report_card)
        db.flush()

        for course_result in course_results:
            get_or_create_audit_log(
                db,
                stats,
                actor_user_id=admin_user.id,
                action="stress_course_result_seeded",
                entity_type="course_result",
                entity_id=course_result.id,
                new_value={
                    "average": course_result.average,
                    "letter_grade": course_result.letter_grade,
                    "term": course_result.term,
                },
            )

        for report_card in report_cards:
            get_or_create_audit_log(
                db,
                stats,
                actor_user_id=admin_user.id,
                action="stress_report_seeded",
                entity_type="report_card",
                entity_id=report_card.id,
                new_value={
                    "status": report_card.status,
                    "overall_average": report_card.overall_average,
                    "gpa": report_card.gpa,
                },
            )

        db.commit()

        stats.print_summary()
        print(f"Stress admin login: stress-admin@school.test / {STRESS_PASSWORD}")
        print(f"Stress parent logins: stress-parent-001..{padded(PARENT_COUNT)}@school.test / {STRESS_PASSWORD}")
        print(f"Stress teacher logins: stress-teacher-001..{padded(TEACHER_COUNT)}@school.test / {STRESS_PASSWORD}")
        print(f"Students per course: {STUDENTS_PER_COURSE}")
        print(f"Approved reports generated/reused for all {REPORT_COUNT} stress students.")
        print("No OpenAI calls or emails were sent.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_large_demo_data()
