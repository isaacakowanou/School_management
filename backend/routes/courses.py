from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import get_current_user, require_admin
from constants import TRIMESTER_TERMS
from database import get_db
from models import Class, Course, CourseResult, Enrollment, Grade, GradeItem, ReportCardCourse, Student, Subject, Teacher, User
from schemas import (
    CourseCloneYearRequest,
    CourseCloneYearResponse,
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    LanguageGroup,
    StatusResponse,
    TermAdvanceCoursePreview,
    TermAdvancePreviewResponse,
    TermAdvanceRequest,
    TermAdvanceResponse,
    TrimesterTerm,
)
from services.grade_calculator import is_beninese_mode
from utils import get_class_or_404, get_current_teacher, get_subject_or_404, to_course_response


router = APIRouter(tags=["courses"])


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_teacher_or_404(db: Session, teacher_id: UUID) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None or teacher.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher


def teacher_can_read_course(db: Session, current_user: User, course: Course) -> bool:
    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def ensure_unique_course_code(db: Session, code: str, course_id: UUID | None = None) -> None:
    query = select(Course).where(Course.code == code)
    if course_id is not None:
        query = query.where(Course.id != course_id)

    existing_course = db.scalar(query)
    if existing_course is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course code already exists")


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


def derived_from_subject(subject: Subject) -> tuple[str, str]:
    """Course display name + language_group derived from a catalog subject.

    The bulletin prints French-section courses under their French names and
    English-section courses under their English names; the section value
    doubles as the course's language_group (feeds the A1.6 three averages).
    """
    if subject.section == LanguageGroup.FRENCH.value:
        return subject.name_fr, subject.section
    return subject.name_en, subject.section


_SUBJECT_LANGUAGE_CONFLICT = "language_group conflicts with the subject's section; omit it or clear subject_id"
_SUBJECT_NAME_CONFLICT = "name is derived from the subject; omit it or clear subject_id"


def course_list_stats(db: Session, courses: list[Course]) -> dict[UUID, dict[str, int]]:
    course_ids = [course.id for course in courses]
    if not course_ids:
        return {}

    stats = {
        course.id: {
            "student_count": 0,
            "grade_item_count": 0,
            "filled_score_count": 0,
            "possible_score_count": 0,
        }
        for course in courses
    }

    student_counts = dict(
        db.execute(
            select(Enrollment.course_id, func.count(func.distinct(Student.id)))
            .join(Student, Student.id == Enrollment.student_id)
            .where(
                Enrollment.course_id.in_(course_ids),
                Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None),
            )
            .group_by(Enrollment.course_id)
        ).all()
    )
    grade_item_counts = dict(
        db.execute(
            select(GradeItem.course_id, func.count(GradeItem.id))
            .join(Course, Course.id == GradeItem.course_id)
            .where(
                GradeItem.course_id.in_(course_ids),
                GradeItem.term == Course.term,
                GradeItem.deleted_at.is_(None),
                Course.deleted_at.is_(None),
            )
            .group_by(GradeItem.course_id)
        ).all()
    )
    filled_score_counts = dict(
        db.execute(
            select(GradeItem.course_id, func.count(Grade.id))
            .join(GradeItem, GradeItem.id == Grade.grade_item_id)
            .join(Course, Course.id == GradeItem.course_id)
            .join(Student, Student.id == Grade.student_id)
            .join(
                Enrollment,
                (Enrollment.student_id == Grade.student_id)
                & (Enrollment.course_id == GradeItem.course_id),
            )
            .where(
                GradeItem.course_id.in_(course_ids),
                GradeItem.term == Course.term,
                Grade.deleted_at.is_(None),
                GradeItem.deleted_at.is_(None),
                Course.deleted_at.is_(None),
                Student.deleted_at.is_(None),
                Enrollment.deleted_at.is_(None),
            )
            .group_by(GradeItem.course_id)
        ).all()
    )

    for course_id in course_ids:
        student_count = student_counts.get(course_id, 0)
        grade_item_count = grade_item_counts.get(course_id, 0)
        stats[course_id] = {
            "student_count": student_count,
            "grade_item_count": grade_item_count,
            "filled_score_count": filled_score_counts.get(course_id, 0),
            "possible_score_count": student_count * grade_item_count,
        }
    return stats


@router.get("", response_model=list[CourseResponse])
def list_courses(
    school_year: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    query = (
        select(Course)
        .options(joinedload(Course.school_class))
        .where(Course.deleted_at.is_(None))
        .order_by(Course.name, Course.code)
    )
    if school_year is not None:
        query = query.where(Course.school_year == school_year)

    if current_user.role == "admin":
        courses = db.scalars(query).all()
        stats = course_list_stats(db, courses)
        return [to_course_response(course, stats.get(course.id)) for course in courses]

    if current_user.role == "teacher":
        teacher = get_current_teacher(db, current_user)
        if teacher is None:
            return []
        courses = db.scalars(query.where(Course.teacher_id == teacher.id)).all()
        stats = course_list_stats(db, courses)
        return [to_course_response(course, stats.get(course.id)) for course in courses]

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseResponse:
    code = clean_required_text(payload.code, "code")
    term = payload.term.value
    school_year = clean_required_text(payload.school_year, "school_year")
    language_group = payload.language_group.value if payload.language_group is not None else None

    if payload.subject_id is not None:
        subject = get_subject_or_404(db, payload.subject_id)
        name, derived_group = derived_from_subject(subject)
        if language_group is not None and language_group != derived_group:
            raise HTTPException(status_code=422, detail=_SUBJECT_LANGUAGE_CONFLICT)
        if payload.name is not None and payload.name.strip() != name:
            raise HTTPException(status_code=422, detail=_SUBJECT_NAME_CONFLICT)
        language_group = derived_group
    else:
        if payload.name is None:
            raise HTTPException(status_code=422, detail="name is required when subject_id is not provided")
        name = clean_required_text(payload.name, "name")

    get_teacher_or_404(db, payload.teacher_id)
    ensure_unique_course_code(db, code)
    if payload.class_id is not None:
        get_class_or_404(db, payload.class_id)

    course = Course(
        name=name,
        code=code,
        teacher_id=payload.teacher_id,
        term=term,
        school_year=school_year,
        language_group=language_group,
        class_id=payload.class_id,
        subject_id=payload.subject_id,
        coefficient=payload.coefficient,
    )
    db.add(course)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_created",
        entity_type="course",
        entity_id=course.id,
        old_value=None,
        new_value={
            "name": course.name,
            "code": course.code,
            "teacher_id": course.teacher_id,
            "term": course.term,
            "school_year": course.school_year,
            "language_group": course.language_group,
            "class_id": course.class_id,
            "subject_id": course.subject_id,
            "coefficient": course.coefficient,
        },
    )
    db.commit()
    db.refresh(course)
    return to_course_response(course)


@router.post("/clone-year", response_model=CourseCloneYearResponse, status_code=status.HTTP_201_CREATED)
def clone_year(
    payload: CourseCloneYearRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseCloneYearResponse:
    """Duplicate all courses from one school year into another (A1.9).

    Copies subject/name, class (remapped by name into the target year),
    language_group, and teacher assignment — no grade items, no enrollments.
    """
    source_year = clean_required_text(payload.source_year, "source_year")
    target_year = clean_required_text(payload.target_year, "target_year")
    if source_year == target_year:
        raise HTTPException(status_code=422, detail="source_year and target_year must differ")

    source_courses = db.scalars(
        select(Course).where(Course.school_year == source_year).order_by(Course.name, Course.code)
        .where(Course.deleted_at.is_(None))
    ).all()
    if not source_courses:
        raise HTTPException(status_code=422, detail="Source year has no courses to clone")

    target_count = db.scalar(
        select(func.count(Course.id)).where(Course.school_year == target_year, Course.deleted_at.is_(None))
    )
    if target_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Target year already has courses",
                "course_count": target_count,
            },
        )

    # Course codes are globally unique across years, so clones get a
    # deterministic year suffix. Collisions are a hard stop, not a skip.
    new_code_by_id = {course.id: f"{course.code}-{target_year}" for course in source_courses}
    taken_codes = sorted(
        db.scalars(select(Course.code).where(Course.code.in_(list(new_code_by_id.values())))).all()
    )
    if taken_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Cloned course codes already exist",
                "codes": taken_codes,
            },
        )

    # Class rows are per-year (unique on name_fr + school_year), so class links
    # are remapped by name into the target year; classes missing there leave
    # the clone's class_id null and are reported back.
    source_class_ids = {c.class_id for c in source_courses if c.class_id is not None}
    source_name_by_class_id = {}
    if source_class_ids:
        source_name_by_class_id = dict(
            db.execute(select(Class.id, Class.name_fr).where(Class.id.in_(source_class_ids))).all()
        )
    target_class_id_by_name = dict(
        db.execute(select(Class.name_fr, Class.id).where(Class.school_year == target_year)).all()
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
                term=source_course.term,
                school_year=target_year,
                language_group=source_course.language_group,
                class_id=target_class_id,
                subject_id=source_course.subject_id,
                coefficient=source_course.coefficient,
            )
        )
    db.flush()

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="courses_cloned_year",
        entity_type="course_clone_batch",
        entity_id=uuid4(),
        old_value=None,
        new_value={
            "source_year": source_year,
            "target_year": target_year,
            "created_count": len(source_courses),
            "unmatched_class_names": sorted(unmatched_class_names),
        },
    )
    db.commit()

    return CourseCloneYearResponse(
        status="ok",
        created_count=len(source_courses),
        unmatched_class_names=sorted(unmatched_class_names),
    )


# NOTE: the advance-term routes are static paths and MUST stay declared before
# the /{course_id} routes below, or FastAPI tries to parse "advance-term" as a
# course UUID (same constraint as /clone-year).


@router.get("/advance-term/preview", response_model=TermAdvancePreviewResponse)
def preview_advance_term(
    school_year: str,
    target_term: TrimesterTerm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TermAdvancePreviewResponse:
    """Readiness report for a school-year-wide trimester change.

    Warnings are informational only — the POST never blocks on them. The
    counts show how complete each course's CLOSING term is before the switch.
    """
    courses = db.scalars(
        select(Course)
        .options(joinedload(Course.school_class))
        .where(Course.school_year == school_year, Course.deleted_at.is_(None))
        .order_by(Course.name, Course.code)
    ).all()

    course_ids = [course.id for course in courses]
    enrolled_by_course: dict[UUID, int] = {}
    results_by_course_term: dict[tuple[UUID, str], int] = {}
    items_by_course_term_type: dict[tuple[UUID, str, str | None], int] = {}
    if course_ids:
        enrolled_by_course = dict(
            db.execute(
                select(Enrollment.course_id, func.count(Enrollment.id))
                .where(Enrollment.course_id.in_(course_ids), Enrollment.deleted_at.is_(None))
                .group_by(Enrollment.course_id)
            ).all()
        )
        results_by_course_term = {
            (course_id, term): count
            for course_id, term, count in db.execute(
                select(CourseResult.course_id, CourseResult.term, func.count(CourseResult.id))
                .where(CourseResult.course_id.in_(course_ids), CourseResult.deleted_at.is_(None))
                .group_by(CourseResult.course_id, CourseResult.term)
            ).all()
        }
        items_by_course_term_type = {
            (course_id, term, item_type): count
            for course_id, term, item_type, count in db.execute(
                select(GradeItem.course_id, GradeItem.term, GradeItem.item_type, func.count(GradeItem.id))
                .where(GradeItem.course_id.in_(course_ids), GradeItem.deleted_at.is_(None))
                .group_by(GradeItem.course_id, GradeItem.term, GradeItem.item_type)
            ).all()
        }

    previews = []
    already_on_target = 0
    for course in courses:
        warnings = []
        if course.term not in TRIMESTER_TERMS:
            warnings.append("non_canonical_term")
        if is_beninese_mode(course):
            for item_type, key in (
                ("INTERRO", "missing_interro"),
                ("DEVOIR", "missing_devoir"),
                ("COMPOSITION", "missing_composition"),
            ):
                if not items_by_course_term_type.get((course.id, course.term, item_type)):
                    warnings.append(key)
        on_target = course.term == target_term.value
        if on_target:
            already_on_target += 1
        previews.append(
            TermAdvanceCoursePreview(
                course_id=course.id,
                code=course.code,
                name=course.name,
                current_term=course.term,
                already_on_target=on_target,
                enrolled_count=enrolled_by_course.get(course.id, 0),
                results_calculated_count=results_by_course_term.get((course.id, course.term), 0),
                warnings=warnings,
            )
        )

    return TermAdvancePreviewResponse(
        school_year=school_year,
        target_term=target_term.value,
        courses=previews,
        total_count=len(previews),
        already_on_target_count=already_on_target,
    )


@router.post("/advance-term", response_model=TermAdvanceResponse)
def advance_term(
    payload: TermAdvanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TermAdvanceResponse:
    """Set every course of a school year to the target trimester.

    Idempotent: courses already on the target term are skipped. Warnings from
    the preview never block — the school calendar wins. Backward moves are
    allowed (mistake recovery) and audit-logged like any other change.
    """
    target = payload.target_term.value
    courses = db.scalars(
        select(Course).where(Course.school_year == payload.school_year, Course.deleted_at.is_(None))
    ).all()

    updated_codes = []
    for course in courses:
        if course.term != target:
            course.term = target
            updated_codes.append(course.code)

    if updated_codes:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="courses_term_advanced",
            entity_type="course_term_advance",
            entity_id=uuid4(),
            old_value=None,
            new_value={
                "school_year": payload.school_year,
                "target_term": target,
                "updated_count": len(updated_codes),
                "skipped_count": len(courses) - len(updated_codes),
                "updated_codes": sorted(updated_codes),
            },
        )
    db.commit()

    return TermAdvanceResponse(
        status="ok",
        school_year=payload.school_year,
        target_term=target,
        updated_count=len(updated_codes),
        skipped_count=len(courses) - len(updated_codes),
    )


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResponse:
    course = db.scalar(
        select(Course)
        .where(Course.id == course_id, Course.deleted_at.is_(None))
        .options(joinedload(Course.school_class))
    )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if current_user.role == "admin" or (
        current_user.role == "teacher" and teacher_can_read_course(db, current_user, course)
    ):
        return to_course_response(course)

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseResponse:
    course = get_course_or_404(db, course_id)
    old_value = {
        "name": course.name,
        "code": course.code,
        "teacher_id": course.teacher_id,
        "term": course.term,
        "school_year": course.school_year,
        "language_group": course.language_group,
        "class_id": course.class_id,
        "subject_id": course.subject_id,
        "coefficient": course.coefficient,
    }

    # Resolve the course's effective subject after this update: an explicit
    # subject_id wins (null clears the link), else the currently linked subject
    # is retained.
    if "subject_id" in payload.model_fields_set:
        subject = get_subject_or_404(db, payload.subject_id) if payload.subject_id is not None else None
    else:
        subject = course.subject

    if payload.code is not None:
        code = clean_required_text(payload.code, "code")
        ensure_unique_course_code(db, code, course_id=course_id)
        course.code = code
    if payload.teacher_id is not None:
        get_teacher_or_404(db, payload.teacher_id)
        course.teacher_id = payload.teacher_id

    if subject is not None:
        # Subject-linked courses keep name and language_group derived from the
        # subject; explicit values that disagree are rejected rather than
        # silently desynced (echoing the derived values back is fine).
        derived_name, derived_group = derived_from_subject(subject)
        if payload.name is not None and payload.name.strip() != derived_name:
            raise HTTPException(status_code=422, detail=_SUBJECT_NAME_CONFLICT)
        if "language_group" in payload.model_fields_set:
            requested = payload.language_group.value if payload.language_group is not None else None
            if requested != derived_group:
                raise HTTPException(status_code=422, detail=_SUBJECT_LANGUAGE_CONFLICT)
        course.subject_id = subject.id
        course.name = derived_name
        course.language_group = derived_group
    else:
        course.subject_id = None
        if payload.name is not None:
            course.name = clean_required_text(payload.name, "name")
        # language_group is nullable: an explicit null clears the tag, while
        # omitting the key leaves it unchanged. The `is not None` guard used for
        # the required fields can't express "clear", so key off whether the
        # client actually sent the field.
        if "language_group" in payload.model_fields_set:
            course.language_group = (
                payload.language_group.value if payload.language_group is not None else None
            )

    if payload.term is not None:
        course.term = payload.term.value
    if payload.school_year is not None:
        course.school_year = clean_required_text(payload.school_year, "school_year")
    if "class_id" in payload.model_fields_set:
        if payload.class_id is not None:
            get_class_or_404(db, payload.class_id)
        course.class_id = payload.class_id

    if payload.coefficient is not None:
        course.coefficient = payload.coefficient

    new_value = {
        "name": course.name,
        "code": course.code,
        "teacher_id": course.teacher_id,
        "term": course.term,
        "school_year": course.school_year,
        "language_group": course.language_group,
        "class_id": course.class_id,
        "subject_id": course.subject_id,
        "coefficient": course.coefficient,
    }
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="course_updated",
            entity_type="course",
            entity_id=course.id,
            old_value=old_value,
            new_value=new_value,
        )

    db.commit()
    db.refresh(course)
    return to_course_response(course)


@router.delete("/{course_id}", response_model=StatusResponse)
def delete_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    course = get_course_or_404(db, course_id)
    enrollment_count = db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == course_id))
    grade_item_count = db.scalar(select(func.count(GradeItem.id)).where(GradeItem.course_id == course_id))
    course_result_count = db.scalar(select(func.count(CourseResult.id)).where(CourseResult.course_id == course_id))
    report_snapshot_count = db.scalar(
        select(func.count(ReportCardCourse.id)).where(ReportCardCourse.course_id == course_id)
    )
    grade_count = db.scalar(
        select(func.count(Grade.id))
        .join(GradeItem, Grade.grade_item_id == GradeItem.id)
        .where(GradeItem.course_id == course_id)
    )
    if enrollment_count or grade_item_count or course_result_count or report_snapshot_count or grade_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Course has roster, grade, result, or report data",
                "enrollment_count": enrollment_count,
                "grade_item_count": grade_item_count,
                "grade_count": grade_count,
                "course_result_count": course_result_count,
                "report_snapshot_count": report_snapshot_count,
            },
        )

    old_value = {
        "name": course.name,
        "code": course.code,
        "teacher_id": course.teacher_id,
        "term": course.term,
        "school_year": course.school_year,
        "language_group": course.language_group,
        "class_id": course.class_id,
        "subject_id": course.subject_id,
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_deleted",
        entity_type="course",
        entity_id=course.id,
        old_value=old_value,
        new_value=None,
    )
    course.deleted_at = func.now()
    db.commit()
    return StatusResponse(status="ok", message="Course moved to Trash")
