"""Manage year-scoped courses, setup cloning, and trimester advancement.

Every Course belongs to one school year and term. Teacher/subject identity is
permanent, while grades, results, and bulletin snapshots are historical data.

Catalog-linked courses derive their display name and language track from the
subject so bulletin grouping cannot drift from the catalog. Year cloning copies
setup only, including grading identity, never grades or enrollments; new-year
clones always begin at the first trimester. Coefficients remain explicit admin
configuration. Trimester preview warnings inform Conseil de classe readiness,
but advancement follows the school calendar and remains idempotent/audited.
Explicit grading-system changes are guarded when active grade items exist;
confirmation acknowledges incompatibility risk but never rewrites those items.
"""

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
    CourseBulkCreateRequest,
    CourseBulkCreateResponse,
    CourseBulkPreviewRequest,
    CourseBulkPreviewResponse,
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
from services.course_setup import (
    active_course_by_setup_key,
    applicable_subjects_for_class,
    course_name_from_subject,
    grading_system_for_class_subject,
    subject_applies_to_class,
    suggested_course_code,
)
from services.school_year_rollover import clean_school_year, clone_course_setup_for_year
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
    return clean_school_year(value, field_name)


def derived_from_subject(subject: Subject) -> tuple[str, str]:
    """Course display name + language_group derived from a catalog subject.

    The bulletin prints French-section courses under their French names and
    English-section courses under their English names; the section value
    doubles as the course's language_group (feeds the A1.6 three averages).
    """
    if subject.section == LanguageGroup.FRENCH.value:
        return subject.name_fr, subject.section
    return subject.name_en, subject.section


def grading_system_for_setup(language_group: str | None, school_class: Class | None) -> str:
    if language_group == "FRENCH" and school_class is not None and school_class.school_level == "college":
        return "BENINESE"
    return "WEIGHTED"


def ensure_class_matches_school_year(school_class: Class | None, school_year: str) -> None:
    if school_class is not None and school_class.school_year != school_year:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "course_class_year_mismatch",
                "message": "Class does not belong to the requested school year",
            },
        )


def ensure_subject_applies(subject: Subject | None, school_class: Class | None) -> None:
    if subject is not None and school_class is not None and not subject_applies_to_class(subject, school_class):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "course_subject_not_applicable",
                "message": "Subject does not apply to the selected class",
            },
        )


def ensure_unique_active_course_setup(
    db: Session,
    *,
    school_year: str,
    class_id: UUID | None,
    subject_id: UUID | None,
    course_id: UUID | None = None,
) -> None:
    if class_id is None or subject_id is None:
        return
    query = select(Course.id).where(
        Course.school_year == school_year,
        Course.class_id == class_id,
        Course.subject_id == subject_id,
        Course.deleted_at.is_(None),
    )
    if course_id is not None:
        query = query.where(Course.id != course_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "course_setup_already_exists",
                "message": "An active course already exists for this class and subject in the school year",
            },
        )


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
    term: str | None = None,
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
    if term is not None:
        if term not in TRIMESTER_TERMS:
            raise HTTPException(status_code=422, detail="term must be a canonical trimester")
        query = query.where(Course.term == term)

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

    if payload.teacher_id is not None:
        get_teacher_or_404(db, payload.teacher_id)
    ensure_unique_course_code(db, code)
    school_class = get_class_or_404(db, payload.class_id) if payload.class_id is not None else None
    ensure_class_matches_school_year(school_class, school_year)
    ensure_subject_applies(subject if payload.subject_id is not None else None, school_class)
    ensure_unique_active_course_setup(
        db,
        school_year=school_year,
        class_id=payload.class_id,
        subject_id=payload.subject_id,
    )

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
        grading_system=(
            payload.grading_system.value
            if payload.grading_system is not None
            else grading_system_for_setup(language_group, school_class)
        ),
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
            "grading_system": course.grading_system,
        },
    )
    db.commit()
    db.refresh(course)
    return to_course_response(course)


@router.post("/bulk-setup/preview", response_model=CourseBulkPreviewResponse)
def preview_bulk_course_setup(
    payload: CourseBulkPreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CourseBulkPreviewResponse:
    school_year = clean_required_text(payload.school_year, "school_year")
    classes = []
    for class_id in dict.fromkeys(payload.class_ids):
        school_class = get_class_or_404(db, class_id)
        ensure_class_matches_school_year(school_class, school_year)
        classes.append(school_class)

    existing_by_key = active_course_by_setup_key(db, school_year, [school_class.id for school_class in classes])
    all_codes = set(db.scalars(select(Course.code)).all())
    rows = []
    existing_count = 0
    for school_class in classes:
        for subject in applicable_subjects_for_class(db, school_class):
            existing = existing_by_key.get((school_class.id, subject.id))
            code = suggested_course_code(school_year, school_class, subject)
            if existing is not None:
                existing_count += 1
            rows.append(
                {
                    "class_id": school_class.id,
                    "class_name": school_class.name_fr,
                    "subject_id": subject.id,
                    "subject_name": course_name_from_subject(subject),
                    "language_group": subject.section,
                    "sort_order": subject.sort_order,
                    "code": existing.code if existing is not None else code,
                    "coefficient": existing.coefficient if existing is not None else 1,
                    "grading_system": (
                        existing.grading_system
                        if existing is not None and existing.grading_system is not None
                        else grading_system_for_class_subject(school_class, subject)
                    ),
                    "teacher_id": existing.teacher_id if existing is not None else None,
                    "already_exists": existing is not None,
                    "existing_course_id": existing.id if existing is not None else None,
                    "code_conflict": existing is None and code in all_codes,
                }
            )

    return CourseBulkPreviewResponse(
        school_year=school_year,
        term=payload.term,
        rows=rows,
        applicable_count=len(rows),
        missing_count=len(rows) - existing_count,
        existing_count=existing_count,
    )


@router.post("/bulk-setup", response_model=CourseBulkCreateResponse, status_code=status.HTTP_201_CREATED)
def create_bulk_course_setup(
    payload: CourseBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseBulkCreateResponse:
    school_year = clean_required_text(payload.school_year, "school_year")
    class_ids = list(dict.fromkeys(item.class_id for item in payload.items))
    existing_by_key = active_course_by_setup_key(db, school_year, class_ids)
    seen_keys = set()
    seen_codes = set()
    failures = []
    prepared = []
    skipped_existing_count = 0

    for item in payload.items:
        school_class = db.get(Class, item.class_id)
        subject = db.get(Subject, item.subject_id)
        key = (item.class_id, item.subject_id)
        if key in existing_by_key:
            skipped_existing_count += 1
            continue
        if key in seen_keys:
            failures.append({
                "class_id": item.class_id,
                "subject_id": item.subject_id,
                "code": "duplicate_selection",
                "message": "The same class and subject were selected more than once",
            })
            continue
        seen_keys.add(key)

        if school_class is None or school_class.deleted_at is not None:
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "class_not_found", "message": "Class not found"})
            continue
        if school_class.school_year != school_year:
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "course_class_year_mismatch", "message": "Class does not belong to the requested school year"})
            continue
        if subject is None or subject.deleted_at is not None:
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "subject_not_found", "message": "Subject not found"})
            continue
        if not subject_applies_to_class(subject, school_class):
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "course_subject_not_applicable", "message": "Subject does not apply to the selected class"})
            continue
        if item.teacher_id is not None:
            teacher = db.get(Teacher, item.teacher_id)
            if teacher is None or teacher.deleted_at is not None:
                failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "teacher_not_found", "message": "Teacher not found"})
                continue

        code = item.code.strip()
        if not code:
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "course_code_required", "message": "Course code cannot be empty"})
            continue
        if code in seen_codes or db.scalar(select(Course.id).where(Course.code == code)) is not None:
            failures.append({"class_id": item.class_id, "subject_id": item.subject_id, "code": "course_code_conflict", "message": f"Course code already exists: {code}"})
            continue
        seen_codes.add(code)
        prepared.append((item, school_class, subject, code))

    if failures:
        serializable_failures = [
            {
                **failure,
                "class_id": str(failure["class_id"]) if failure.get("class_id") is not None else None,
                "subject_id": str(failure["subject_id"]) if failure.get("subject_id") is not None else None,
            }
            for failure in failures
        ]
        raise HTTPException(
            status_code=422,
            detail={"code": "bulk_course_validation_failed", "validation_failures": serializable_failures},
        )

    created_courses = []
    for item, school_class, subject, code in prepared:
        course = Course(
            name=course_name_from_subject(subject),
            code=code,
            teacher_id=item.teacher_id,
            term=payload.term.value,
            school_year=school_year,
            language_group=subject.section,
            class_id=school_class.id,
            subject_id=subject.id,
            coefficient=item.coefficient,
            grading_system=item.grading_system.value,
        )
        db.add(course)
        created_courses.append(course)

    db.flush()
    for course in created_courses:
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
                "grading_system": course.grading_system,
                "bulk_setup": True,
            },
        )
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="courses_bulk_created",
        entity_type="course_setup_batch",
        entity_id=uuid4(),
        old_value=None,
        new_value={
            "school_year": school_year,
            "term": payload.term.value,
            "created_count": len(created_courses),
            "skipped_existing_count": skipped_existing_count,
            "created_course_ids": [course.id for course in created_courses],
        },
    )
    db.commit()

    return CourseBulkCreateResponse(
        status="ok",
        created_count=len(created_courses),
        skipped_existing_count=skipped_existing_count,
        created_course_ids=[course.id for course in created_courses],
        validation_failures=[],
    )


@router.post("/clone-year", response_model=CourseCloneYearResponse, status_code=status.HTTP_201_CREATED)
def clone_year(
    payload: CourseCloneYearRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseCloneYearResponse:
    """Duplicate all courses from one school year into another (A1.9).

    Copies every reusable Course setup field. Class is remapped by name into
    the target year, term is deliberately reset, and no grade items or
    enrollments are copied.
    """
    source_year = clean_required_text(payload.source_year, "source_year")
    target_year = clean_required_text(payload.target_year, "target_year")
    created_count, skipped_count, unmatched_class_names = clone_course_setup_for_year(db, source_year, target_year)
    nothing_to_do = created_count == 0
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
            "created_count": created_count,
            "skipped_count": skipped_count,
            "unmatched_class_names": unmatched_class_names,
            "nothing_to_do": nothing_to_do,
        },
    )
    db.commit()

    return CourseCloneYearResponse(
        status="ok",
        created_count=created_count,
        skipped_count=skipped_count,
        nothing_to_do=nothing_to_do,
        unmatched_class_names=unmatched_class_names,
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
    This is a Conseil de classe operation rather than ordinary course editing:
    GGFK advances the school's courses together at each trimester boundary.
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
    allowed for mistake recovery and audit-logged like any other change. Do not
    turn readiness warnings into a hard gate; incomplete grade/bulletin guards
    already protect official outputs while the calendar must still advance.
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
        "grading_system": course.grading_system,
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
    if "teacher_id" in payload.model_fields_set:
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
    effective_class = course.school_class
    if "class_id" in payload.model_fields_set:
        if payload.class_id is not None:
            effective_class = get_class_or_404(db, payload.class_id)
        else:
            effective_class = None
        course.class_id = payload.class_id

    ensure_class_matches_school_year(effective_class, course.school_year)
    ensure_subject_applies(subject, effective_class)
    ensure_unique_active_course_setup(
        db,
        school_year=course.school_year,
        class_id=course.class_id,
        subject_id=subject.id if subject is not None else None,
        course_id=course.id,
    )

    if payload.coefficient is not None:
        course.coefficient = payload.coefficient

    effective_grading_system = course.grading_system or (
        "BENINESE" if is_beninese_mode(course) else "WEIGHTED"
    )
    if payload.grading_system is not None and payload.grading_system.value != effective_grading_system:
        active_item_count = db.scalar(
            select(func.count(GradeItem.id)).where(
                GradeItem.course_id == course.id,
                GradeItem.deleted_at.is_(None),
            )
        ) or 0
        if active_item_count and not payload.confirm_grading_system_change:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "grading_system_change_requires_confirmation",
                    "message": "Changing grading system may not match existing grade items",
                    "grade_item_count": active_item_count,
                },
            )
    if payload.grading_system is not None:
        course.grading_system = payload.grading_system.value

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
        "grading_system": course.grading_system,
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
