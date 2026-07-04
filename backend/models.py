import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
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
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parent_profile: Mapped["Parent | None"] = orm_relationship(back_populates="user")
    teacher_profile: Mapped["Teacher | None"] = orm_relationship(back_populates="user")
    approved_report_cards: Mapped[list["ReportCard"]] = orm_relationship(back_populates="approved_by_admin")
    audit_logs: Mapped[list["AuditLog"]] = orm_relationship(back_populates="actor")


class Class(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("name_fr", "school_year", name="uq_class_name_fr_school_year"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_fr: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Reuses the SchoolLevel enum values (maternelle/primaire/college); validated
    # via Pydantic, stored as a plain string (same Option C pattern as
    # Student.school_level).
    school_level: Mapped[str] = mapped_column(String(20), nullable=False)
    stream: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    students: Mapped[list["Student"]] = orm_relationship(back_populates="school_class")
    courses: Mapped[list["Course"]] = orm_relationship(back_populates="school_class")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    school_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    educmaster_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parent_links: Mapped[list["StudentParent"]] = orm_relationship(back_populates="student")
    enrollments: Mapped[list["Enrollment"]] = orm_relationship(back_populates="student")
    grades: Mapped[list["Grade"]] = orm_relationship(back_populates="student")
    course_results: Mapped[list["CourseResult"]] = orm_relationship(back_populates="student")
    report_cards: Mapped[list["ReportCard"]] = orm_relationship(back_populates="student")
    school_class: Mapped["Class | None"] = orm_relationship(back_populates="students")


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    student: Mapped["Student"] = orm_relationship(back_populates="parent_links")
    parent: Mapped["Parent"] = orm_relationship(back_populates="student_links")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = orm_relationship(back_populates="teacher_profile")
    courses: Mapped[list["Course"]] = orm_relationship(back_populates="teacher")
    submitted_grades: Mapped[list["Grade"]] = orm_relationship(back_populates="submitted_by_teacher")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        # name_fr alone is not unique: Mathématique / Informatique legitimately
        # appear in both the FRENCH and ENGLISH sections of the same cycle.
        UniqueConstraint("name_fr", "level_group", "section", name="uq_subject_name_fr_level_group_section"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_fr: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    # FRENCH / ENGLISH bulletin section. Same values as Course.language_group:
    # a course created from a subject inherits this as its language_group, which
    # is what feeds the Moyenne française / anglaise buckets (A1.6). Validated
    # via Pydantic, stored as a plain string (Option C, like Class.school_level).
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    # NURSERY / PRIMARY / COLLEGE_FIRST_CYCLE / COLLEGE_SECOND_CYCLE.
    level_group: Mapped[str] = mapped_column(String(30), nullable=False)
    # Position within its section on the paper bulletin.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Class names (from the locked 18-class taxonomy) this subject is limited
    # to; null means every class in its level_group. Only exceptions set it
    # (Espagnol -> 4ème/3ème, Etudes sociales -> 6ème/5ème). none_as_null keeps
    # "no restriction" a real SQL NULL instead of JSON 'null' text.
    applicable_classes: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    courses: Mapped[list["Course"]] = orm_relationship(back_populates="subject")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    # A1.5 prep for A1.6 (three averages): which language track this course
    # belongs to. Nullable, no default — existing courses stay null until an
    # admin tags them from the UI. Enforced via Pydantic enum, not a DB
    # constraint (same Option C pattern as Student.school_level).
    language_group: Mapped[str | None] = mapped_column(String(20), nullable=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True
    )
    # A1.9: catalog subject this course was created from. Nullable — free-text
    # courses (and all pre-A1.9 rows) stay null; name stays the operative
    # display column either way.
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    teacher: Mapped["Teacher"] = orm_relationship(back_populates="courses")
    subject: Mapped["Subject | None"] = orm_relationship(back_populates="courses")
    enrollments: Mapped[list["Enrollment"]] = orm_relationship(back_populates="course")
    grade_items: Mapped[list["GradeItem"]] = orm_relationship(back_populates="course")
    course_results: Mapped[list["CourseResult"]] = orm_relationship(back_populates="course")
    report_card_courses: Mapped[list["ReportCardCourse"]] = orm_relationship(back_populates="course")
    school_class: Mapped["Class | None"] = orm_relationship(back_populates="courses")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_student_course_enrollment"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
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
    # Grade scale this row's average is on: "20" for results calculated after the
    # A1.2 switch, "100" for historical results. Nullable at the DB level (added
    # nullable-first); the ORM always supplies a value.
    scale: Mapped[str] = mapped_column(String(10), nullable=True, default="20", server_default="20")
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    student: Mapped["Student"] = orm_relationship(back_populates="course_results")
    course: Mapped["Course"] = orm_relationship(back_populates="course_results")


class ReportCard(Base):
    __tablename__ = "report_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    school_year: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_average: Mapped[float] = mapped_column(Float, nullable=False)
    # A1.6 three averages, all on the /20 scale. Nullable: a language track with
    # no tagged courses stays null, and historical reports predate the feature.
    # overall_average is retained as the legacy all-courses mean (staleness +
    # back-compat); these three are computed alongside it.
    french_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    english_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    bilingual_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Grade scale this snapshot's numbers are on: "20" for reports generated
    # after the A1.2 switch, "100" for historical reports. Nullable at the DB
    # level (added nullable-first); the ORM always supplies a value.
    scale: Mapped[str] = mapped_column(String(10), nullable=True, default="20", server_default="20")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A1.7a report-level comments (bilingual teacher + principal). Nullable Text;
    # historical reports predate the feature and stay null.
    teacher_comment_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_comment_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    principal_comment_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    principal_comment_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = orm_relationship(back_populates="report_cards")
    approved_by_admin: Mapped["User | None"] = orm_relationship(back_populates="approved_report_cards")
    courses: Mapped[list["ReportCardCourse"]] = orm_relationship(back_populates="report_card")
    conduct_items: Mapped[list["ReportConductItem"]] = orm_relationship(
        back_populates="report_card", cascade="all, delete-orphan"
    )
    work_habit_items: Mapped[list["ReportWorkHabitItem"]] = orm_relationship(
        back_populates="report_card", cascade="all, delete-orphan"
    )
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="courses")
    course: Mapped["Course"] = orm_relationship(back_populates="report_card_courses")


class ReportConductItem(Base):
    __tablename__ = "report_conduct_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("report_cards.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # Reuses the BISC 9-letter grade codes; nullable so an unassessed item can be
    # stored, though the write path only persists assessed (non-null) rows.
    letter_grade: Mapped[str | None] = mapped_column(String(5), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="conduct_items")


class ReportWorkHabitItem(Base):
    __tablename__ = "report_work_habit_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("report_cards.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(String(50), nullable=False)
    letter_grade: Mapped[str | None] = mapped_column(String(5), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="work_habit_items")


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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deletion_batches.id"), nullable=True
    )

    report_card: Mapped["ReportCard"] = orm_relationship(back_populates="ai_warnings")


class DeletionBatch(Base):
    __tablename__ = "deletion_batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_label: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    restored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    restored_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    counts_json: Mapped[dict] = mapped_column(JSON, nullable=False)


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
