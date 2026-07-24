"""Create a new school year from the canonical class taxonomy and setup data.

The rollover flow is setup-only: it creates classes, optionally clones course
configuration, and never copies enrollments, grades, results, or bulletins.
"""

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from constants import GGFK_CLASSES, TRIMESTER_TERMS, normalize_class_name
from models import Class, Course, User
from services.grade_calculator import is_beninese_mode


def clean_school_year(value: str, field_name: str = "school_year") -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be empty")
    return cleaned


def create_ggfk_classes_for_year(db: Session, school_year: str) -> tuple[list[str], list[str]]:
    existing_keys = {
        normalize_class_name(name)
        for name in db.scalars(
            select(Class.name_fr).where(Class.school_year == school_year, Class.deleted_at.is_(None))
        ).all()
    }

    created: list[str] = []
    skipped: list[str] = []
    for entry in GGFK_CLASSES:
        if normalize_class_name(entry["name_fr"]) in existing_keys:
            skipped.append(entry["name_fr"])
            continue
        db.add(
            Class(
                name_fr=entry["name_fr"],
                name_en=entry["name_en"],
                school_level=entry["school_level"],
                stream=entry["stream"],
                sort_order=entry["sort_order"],
                school_year=school_year,
            )
        )
        created.append(entry["name_fr"])
    return created, skipped


def latest_course_school_year_before(db: Session, target_year: str) -> str | None:
    return db.scalar(
        select(func.max(Course.school_year)).where(
            Course.school_year < target_year,
            Course.deleted_at.is_(None),
        )
    )


def clone_course_setup_for_year(db: Session, source_year: str, target_year: str) -> tuple[int, list[str]]:
    if source_year == target_year:
        raise HTTPException(status_code=422, detail="source_year and target_year must differ")

    source_courses = db.scalars(
        select(Course)
        .options(joinedload(Course.school_class))
        .where(Course.school_year == source_year, Course.deleted_at.is_(None))
        .order_by(Course.name, Course.code)
    ).all()
    if not source_courses:
        raise HTTPException(status_code=422, detail="Source year has no courses to clone")

    target_count = db.scalar(
        select(func.count(Course.id)).where(Course.school_year == target_year, Course.deleted_at.is_(None))
    )
    if target_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Target year already has courses", "course_count": target_count},
        )

    new_code_by_id = {course.id: f"{course.code}-{target_year}" for course in source_courses}
    taken_codes = sorted(
        db.scalars(select(Course.code).where(Course.code.in_(list(new_code_by_id.values())))).all()
    )
    if taken_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Cloned course codes already exist", "codes": taken_codes},
        )

    source_class_ids = {course.class_id for course in source_courses if course.class_id is not None}
    source_name_by_class_id = {}
    if source_class_ids:
        source_name_by_class_id = dict(
            db.execute(select(Class.id, Class.name_fr).where(Class.id.in_(source_class_ids))).all()
        )
    target_class_id_by_name = dict(
        db.execute(select(Class.name_fr, Class.id).where(Class.school_year == target_year, Class.deleted_at.is_(None))).all()
    )

    unmatched_class_names = set()
    for source_course in source_courses:
        target_class_id = None
        if source_course.class_id is not None:
            class_name = source_name_by_class_id.get(source_course.class_id)
            target_class_id = target_class_id_by_name.get(class_name)
            if target_class_id is None:
                unmatched_class_names.add(class_name)
        db.add(
            Course(
                name=source_course.name,
                code=new_code_by_id[source_course.id],
                teacher_id=source_course.teacher_id,
                term=TRIMESTER_TERMS[0],
                school_year=target_year,
                language_group=source_course.language_group,
                class_id=target_class_id,
                subject_id=source_course.subject_id,
                coefficient=source_course.coefficient,
                grading_system=(
                    source_course.grading_system
                    or ("BENINESE" if is_beninese_mode(source_course) else "WEIGHTED")
                ),
            )
        )
    return len(source_courses), sorted(name for name in unmatched_class_names if name)


def audit_rollover(
    db: Session,
    *,
    current_user: User,
    school_year: str,
    created_classes: list[str],
    skipped_classes: list[str],
    source_school_year: str | None,
    cloned_course_count: int,
    unmatched_class_names: list[str],
) -> None:
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="school_year_created",
        entity_type="school_year",
        entity_id=uuid4(),
        old_value=None,
        new_value={
            "school_year": school_year,
            "created_classes": created_classes,
            "skipped_classes": skipped_classes,
            "source_school_year": source_school_year,
            "cloned_course_count": cloned_course_count,
            "unmatched_class_names": unmatched_class_names,
        },
    )
