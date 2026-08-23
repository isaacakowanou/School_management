"""Build and validate catalog-backed course setup for one or more classes.

Subjects are permanent catalog data; courses are year-scoped offerings. A
catalog subject applies through the locked class taxonomy and may have explicit
class exceptions. Bulk setup never creates enrollments, grade items, grades, or
results. Active ``(school_year, class_id, subject_id)`` is the logical identity.
"""

import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from constants import level_group_for_class_name, normalize_class_name
from models import Class, Course, Subject


def subject_applies_to_class(subject: Subject, school_class: Class) -> bool:
    level_group = level_group_for_class_name(school_class.name_fr)
    if not level_group or subject.level_group != level_group:
        return False
    if subject.applicable_classes is None:
        return True
    class_key = normalize_class_name(school_class.name_fr)
    return class_key in {normalize_class_name(name) for name in subject.applicable_classes}


def applicable_subjects_for_class(db: Session, school_class: Class) -> list[Subject]:
    subjects = list(
        db.scalars(
            select(Subject)
            .where(Subject.deleted_at.is_(None))
            .order_by(Subject.section, Subject.sort_order, Subject.name_fr)
        ).all()
    )
    return [subject for subject in subjects if subject_applies_to_class(subject, school_class)]


def course_name_from_subject(subject: Subject) -> str:
    return subject.name_fr if subject.section == "FRENCH" else subject.name_en


def grading_system_for_class_subject(school_class: Class, subject: Subject) -> str:
    if subject.section == "FRENCH" and school_class.school_level == "college":
        return "BENINESE"
    return "WEIGHTED"


def suggested_course_code(school_year: str, school_class: Class, subject: Subject) -> str:
    def slug(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^A-Z0-9]+", "-", ascii_value.upper()).strip("-")

    section = "FR" if subject.section == "FRENCH" else "EN"
    return f"{slug(school_year)}-{slug(school_class.name_fr)}-{section}-{subject.sort_order:02d}"[:50]


def active_course_by_setup_key(
    db: Session, school_year: str, class_ids: list[UUID]
) -> dict[tuple[UUID, UUID], Course]:
    if not class_ids:
        return {}
    courses = db.scalars(
        select(Course).where(
            Course.school_year == school_year,
            Course.class_id.in_(class_ids),
            Course.subject_id.is_not(None),
            Course.deleted_at.is_(None),
        )
    ).all()
    return {(course.class_id, course.subject_id): course for course in courses}
