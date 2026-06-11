import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship as orm_relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parent_profile: Mapped["Parent | None"] = orm_relationship(back_populates="user")
    teacher_profile: Mapped["Teacher | None"] = orm_relationship(back_populates="user")
    approved_report_cards: Mapped[list["ReportCard"]] = orm_relationship(back_populates="approved_by_admin")
    audit_logs: Mapped[list["AuditLog"]] = orm_relationship(back_populates="actor")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(50), nullable=False)
    school_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parent_links: Mapped[list["StudentParent"]] = orm_relationship(back_populates="student")
    enrollments: Mapped[list["Enrollment"]] = orm_relationship(back_populates="student")
    grades: Mapped[list["Grade"]] = orm_relationship(back_populates="student")
    course_results: Mapped[list["CourseResult"]] = orm_relationship(back_populates="student")
    report_cards: Mapped[list["ReportCard"]] = orm_relationship(back_populates="student")


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = orm_relationship(back_populates="parent_profile")
    student_links: Mapped[list["StudentParent"]] = orm_relationship(back_populates="parent")


class StudentParent(Base):
    __tablename__ = "student_parents"
    __table_args__ = (UniqueConstraint("student_id", "parent_id", name="uq_student_parent"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    parent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("parents.id"), nullable=False)
    relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    student: Mapped["Student"] = orm_relationship(back_populates="parent_links")
    parent: Mapped["Parent"] = orm_relationship(back_populates="student_links")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = orm_relationship(back_populates="teacher_profile")
    courses: Mapped[list["Course"]] = orm_relationship(back_populates="teacher")
    submitted_grades: Mapped[list["Grade"]] = orm_relationship(back_populates="submitted_by_teacher")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(50), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    teacher: Mapped["Teacher"] = orm_relationship(back_populates="courses")
    enrollments: Mapped[list["Enrollment"]] = orm_relationship(back_populates="course")
    grade_items: Mapped[list["GradeItem"]] = orm_relationship(back_populates="course")
    course_results: Mapped[list["CourseResult"]] = orm_relationship(back_populates="course")
    report_card_courses: Mapped[list["ReportCardCourse"]] = orm_relationship(back_populates="course")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_student_course_enrollment"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    student: Mapped["Student"] = orm_relationship(back_populates="enrollments")
    course: Mapped["Course"] = orm_relationship(back_populates="enrollments")


class GradeItem(Base):
    __tablename__ = "grade_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    course: Mapped["Course"] = orm_relationship(back_populates="grade_items")
    grades: Mapped[list["Grade"]] = orm_relationship(back_populates="grade_item")


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = (UniqueConstraint("student_id", "grade_item_id", name="uq_student_grade_item"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    grade_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("grade_items.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    submitted_by_teacher_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teachers.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = orm_relationship(back_populates="grades")
    grade_item: Mapped["GradeItem"] = orm_relationship(back_populates="grades")
    submitted_by_teacher: Mapped["Teacher"] = orm_relationship(back_populates="submitted_grades")


class CourseResult(Base):
    __tablename__ = "course_results"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "term", name="uq_student_course_result_term"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    average: Mapped[float] = mapped_column(Float, nullable=False)
    letter_grade: Mapped[str] = mapped_column(String(5), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    student: Mapped["Student"] = orm_relationship(back_populates="course_results")
    course: Mapped["Course"] = orm_relationship(back_populates="course_results")


class ReportCard(Base):
    __tablename__ = "report_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_average: Mapped[float] = mapped_column(Float, nullable=False)
    gpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = orm_relationship(back_populates="report_cards")
    approved_by_admin: Mapped["User | None"] = orm_relationship(back_populates="approved_report_cards")
    courses: Mapped[list["ReportCardCourse"]] = orm_relationship(back_populates="report_card")
    ai_warnings: Mapped[list["AIWarning"]] = orm_relationship(back_populates="report_card")


class ReportCardCourse(Base):
    __tablename__ = "report_card_courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("report_cards.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(200), nullable=False)
    average: Mapped[float] = mapped_column(Float, nullable=False)
    letter_grade: Mapped[str] = mapped_column(String(5), nullable=False)

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="courses")
    course: Mapped["Course"] = orm_relationship(back_populates="report_card_courses")


class AIWarning(Base):
    __tablename__ = "ai_warnings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("report_cards.id"), nullable=False
    )
    warning_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="ai_warnings")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    actor: Mapped["User"] = orm_relationship(back_populates="audit_logs")
