"""Idempotent legacy development seed, invoked explicitly rather than at startup.

It creates recognizable local accounts and rewrites those seed users to the
shared development password for repeatable access; never point it at production.
Freshly created course/items use the canonical first trimester; existing rows
remain untouched because this seed intentionally does not migrate local data.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import hash_password, verify_password
from database import SessionLocal
from models import Course, Enrollment, GradeItem, Parent, Student, StudentParent, Teacher, User


DEV_PASSWORD = "dev-password-123"


def password_matches_dev_password(password_hash: str) -> bool:
    try:
        return verify_password(DEV_PASSWORD, password_hash)
    except Exception:
        return False


def get_or_create_user(db: Session, *, name: str, email: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user:
        if not password_matches_dev_password(user.password_hash):
            user.password_hash = hash_password(DEV_PASSWORD)
        return user

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(DEV_PASSWORD),
        role=role,
    )
    db.add(user)
    return user


def get_or_create_teacher(db: Session, *, user: User, employee_number: str) -> Teacher:
    teacher = db.scalar(
        select(Teacher).where(
            Teacher.employee_number == employee_number,
            Teacher.deleted_at.is_(None),
        )
    )
    if teacher:
        return teacher

    teacher = Teacher(user=user, employee_number=employee_number)
    db.add(teacher)
    return teacher


def get_or_create_parent(db: Session, *, user: User, phone: str) -> Parent:
    parent = db.scalar(select(Parent).where(Parent.user == user))
    if parent:
        return parent

    parent = Parent(user=user, phone=phone)
    db.add(parent)
    return parent


def get_or_create_student(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    student_number: str,
) -> Student:
    student = db.scalar(select(Student).where(Student.student_number == student_number))
    if student:
        return student

    student = Student(
        first_name=first_name,
        last_name=last_name,
        student_number=student_number,
    )
    db.add(student)
    return student


def get_or_create_course(db: Session, *, teacher: Teacher) -> Course:
    course = db.scalar(select(Course).where(Course.code == "MATH-12-FALL-2026"))
    if course:
        return course

    course = Course(
        name="Mathematics",
        code="MATH-12-FALL-2026",
        teacher=teacher,
        term="1er Trimestre",
        school_year="2026-2027",
    )
    db.add(course)
    return course


def get_or_create_grade_item(
    db: Session,
    *,
    course: Course,
    title: str,
    category: str,
    max_score: float,
    weight: float,
) -> GradeItem:
    grade_item = db.scalar(
        select(GradeItem).where(
            GradeItem.course == course,
            GradeItem.title == title,
        )
    )
    if grade_item:
        return grade_item

    grade_item = GradeItem(
        course=course,
        title=title,
        category=category,
        max_score=max_score,
        weight=weight,
        term="1er Trimestre",
    )
    db.add(grade_item)
    return grade_item


def get_or_create_enrollment(db: Session, *, student: Student, course: Course) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student == student,
            Enrollment.course == course,
        )
    )
    if enrollment:
        return enrollment

    enrollment = Enrollment(student=student, course=course)
    db.add(enrollment)
    return enrollment


def get_or_create_student_parent(db: Session, *, student: Student, parent: Parent) -> StudentParent:
    student_parent = db.scalar(
        select(StudentParent).where(
            StudentParent.student == student,
            StudentParent.parent == parent,
        )
    )
    if student_parent:
        return student_parent

    student_parent = StudentParent(student=student, parent=parent, relationship="Guardian")
    db.add(student_parent)
    return student_parent


def seed() -> None:
    db = SessionLocal()
    try:
        admin_user = get_or_create_user(
            db,
            name="Admin User",
            email="admin@school.test",
            role="admin",
        )
        teacher_user = get_or_create_user(
            db,
            name="Taylor Teacher",
            email="teacher@school.test",
            role="teacher",
        )
        parent_user = get_or_create_user(
            db,
            name="Pat Parent",
            email="parent@school.test",
            role="parent",
        )

        db.flush()

        teacher = get_or_create_teacher(db, user=teacher_user, employee_number="TCH001")
        parent = get_or_create_parent(db, user=parent_user, phone="555-0100")

        students = [
            get_or_create_student(
                db,
                first_name=first_name,
                last_name="Student",
                student_number=student_number,
            )
            for first_name, student_number in [
                ("Isaac", "STU001"),
                ("Amina", "STU002"),
                ("Noah", "STU003"),
                ("Maya", "STU004"),
                ("Liam", "STU005"),
            ]
        ]

        db.flush()

        course = get_or_create_course(db, teacher=teacher)
        db.flush()

        for title, category, weight in [
            ("Homework", "Homework", 0.30),
            ("Midterm", "Midterm", 0.30),
            ("Final", "Final", 0.40),
        ]:
            get_or_create_grade_item(
                db,
                course=course,
                title=title,
                category=category,
                max_score=100,
                weight=weight,
            )

        for student in students:
            get_or_create_enrollment(db, student=student, course=course)

        get_or_create_student_parent(db, student=students[0], parent=parent)

        db.commit()

        counts = {
            "users": db.scalar(select(func.count()).select_from(User)),
            "teachers": db.scalar(select(func.count()).select_from(Teacher)),
            "parents": db.scalar(select(func.count()).select_from(Parent)),
            "students": db.scalar(select(func.count()).select_from(Student)),
            "courses": db.scalar(select(func.count()).select_from(Course)),
            "grade_items": db.scalar(select(func.count()).select_from(GradeItem)),
            "enrollments": db.scalar(select(func.count()).select_from(Enrollment)),
            "student_parents": db.scalar(select(func.count()).select_from(StudentParent)),
        }

        print("Seed data ready.")
        for table_name, count in counts.items():
            print(f"{table_name}: {count}")

        _ = admin_user
    finally:
        db.close()


if __name__ == "__main__":
    seed()
