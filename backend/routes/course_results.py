"""Calculate and store a course's results for one requested trimester.

The explicit course grading_system selects the engine, with French-college
inference only for legacy courses that lack it. Beninese items follow the
Interro -> Moy_Int -> MCC -> Moy chain, while weighted courses use item weights.
An omitted term uses course.term; missing scores skip that student and invalidate
the old result for that term rather than silently count missing work as zero.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from audit import create_audit_log
from constants import normalize_term
from database import get_db
from models import Course, CourseResult, Enrollment, Grade, GradeItem, Student, User
from schemas import (
    CourseResultCalculationRequest,
    CourseResultCalculationResponse,
    CourseResultResponse,
    SkippedCourseResultStudent,
    TrimesterTerm,
)
from services.grade_calculator import (
    calculate_beninese_average,
    calculate_course_average,
    get_letter_grade,
    is_beninese_mode,
)
from utils import get_current_teacher, historical_class_name_for_course


router = APIRouter(tags=["course results"])


def to_course_result_response(course_result: CourseResult) -> CourseResultResponse:
    """Return stored result values with student identity and course-based historical class labels."""
    student = course_result.student
    course = course_result.course
    return CourseResultResponse(
        id=course_result.id,
        student_id=course_result.student_id,
        student_name=f"{student.first_name} {student.last_name}" if student else None,
        student_number=student.student_number if student else None,
        academic_status=student.academic_status if student else None,
        historical_class_name=historical_class_name_for_course(course),
        historical_school_year=course.school_year if course else None,
        course_id=course_result.course_id,
        term=course_result.term,
        average=course_result.average,
        letter_grade=course_result.letter_grade,
        scale=course_result.scale,
        moy_int=course_result.moy_int,
        mcc=course_result.mcc,
        devoir_score=course_result.devoir_score,
        composition_score=course_result.composition_score,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    """Return a non-deleted course by ID or raise 404; ownership is checked separately."""
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    """Return a non-deleted student by ID or raise 404, including graduated students."""
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def can_access_course_results(db: Session, current_user: User, course: Course) -> bool:
    """Return True for an admin or the course's assigned active teacher, otherwise False."""
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def get_teacher_course_ids(db: Session, current_user: User) -> list[UUID]:
    """Return IDs of non-deleted courses assigned to this user's teacher profile."""
    teacher = get_current_teacher(db, current_user)
    if teacher is None:
        return []

    return list(db.scalars(select(Course.id).where(Course.teacher_id == teacher.id, Course.deleted_at.is_(None))).all())


def validate_course_grade_items(grade_items: list[GradeItem], beninese: bool, term: str) -> None:
    """Validate the selected term's item set or raise a clear 400.

    Beninese mode requires Interros and exactly one Devoir/Composition. Weighted
    mode delegates range and total-weight checks to the calculator using full scores.
    """
    if not grade_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course has no grade items for {term}",
        )

    # Shape validation is repeated at calculation time because historical or
    # imported rows may bypass today's create-route guard. Otherwise the
    # Ministry formula could run over a mixed or incomplete item set.
    if beninese:
        interros = [item for item in grade_items if item.item_type == "INTERRO"]
        devoirs = [item for item in grade_items if item.item_type == "DEVOIR"]
        compositions = [item for item in grade_items if item.item_type == "COMPOSITION"]
        if not interros:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Beninese-mode course has no Interro grade items for {term}",
            )
        if len(devoirs) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Beninese-mode course must have exactly one Devoir for {term}",
            )
        if len(compositions) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Beninese-mode course must have exactly one Composition for {term}",
            )
    else:
        try:
            calculate_course_average(
                [
                    {
                        "score": grade_item.max_score,
                        "max_score": grade_item.max_score,
                        "weight": grade_item.weight,
                    }
                    for grade_item in grade_items
                ]
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def terms_match(term: str | None, expected_term: str | None) -> bool:
    """Return whether two term values match directly or normalize to the same trimester."""
    return term == expected_term or (
        normalize_term(term) is not None
        and normalize_term(expected_term) is not None
        and normalize_term(term) == normalize_term(expected_term)
    )


def get_term_equivalent_course_results(
    db: Session,
    *,
    student_id: UUID,
    course_id: UUID,
    term: str,
    active_only: bool = False,
) -> list[CourseResult]:
    """Return this student's course results whose terms match the requested trimester.

    Include soft-deleted rows unless active_only is requested, allowing recalculation
    to reuse a historical row instead of creating duplicates.
    """
    query = select(CourseResult).where(
        CourseResult.student_id == student_id,
        CourseResult.course_id == course_id,
    )
    if active_only:
        query = query.where(CourseResult.deleted_at.is_(None))

    return [
        result
        for result in db.scalars(query).all()
        if terms_match(result.term, term)
    ]


def get_course_result_for_recalculation(
    db: Session,
    *,
    student_id: UUID,
    course: Course,
    term: str,
) -> CourseResult | None:
    """Return the best existing result for this student/course/term, or None.

    Prefer the exact term spelling, then an active row, so recalculation can reuse
    legacy or soft-deleted results.
    """
    candidates = get_term_equivalent_course_results(
        db,
        student_id=student_id,
        course_id=course.id,
        term=term,
    )
    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda result: (
            result.term != term,
            result.deleted_at is not None,
        ),
    )[0]


def get_course_grade_items(db: Session, course: Course, term: str) -> list[GradeItem]:
    # Only the requested trimester's grade items may feed its average.
    # Items tagged for another trimester
    # (prepared in advance, or left over after the term advanced) are excluded.
    """Return and validate active items for exactly the requested course and term.

    Never substitute course.term for an explicitly requested historical trimester.
    """
    grade_items = db.scalars(
        select(GradeItem)
        .where(
            GradeItem.course_id == course.id,
            GradeItem.term == term,
            GradeItem.deleted_at.is_(None),
        )
        .order_by(GradeItem.created_at)
    ).all()
    validate_course_grade_items(list(grade_items), is_beninese_mode(course), term)
    return list(grade_items)


def get_enrolled_students_for_course(db: Session, course: Course) -> list[Student]:
    """Return non-deleted students with active enrollments in the course, including graduates."""
    return list(
        db.scalars(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Enrollment.course_id == course.id,
                Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None),
            )
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def get_selected_enrolled_students(db: Session, course: Course, student_ids: list[UUID]) -> list[Student]:
    """Return the selected enrolled students once each, or raise 400 for missing enrollment.

    An empty selection is rejected; this prevents partial recalculation from quietly
    accepting an unrelated student ID.
    """
    unique_student_ids = list(dict.fromkeys(student_ids))
    if not unique_student_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one student_id is required")

    students = list(
        db.scalars(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Enrollment.course_id == course.id,
                Student.id.in_(unique_student_ids),
                Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None),
            )
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )
    found_student_ids = {student.id for student in students}
    if any(student_id not in found_student_ids for student_id in unique_student_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more students are not enrolled in this course",
        )

    return students


def calculate_results_for_students(
    db: Session,
    *,
    course: Course,
    grade_items: list[GradeItem],
    students: list[Student],
    term: str,
    beninese: bool = False,
) -> tuple[list[CourseResult], list[SkippedCourseResultStudent], list[CourseResult]]:
    """Stage one term's results for the supplied course, items, and students.

    Delegate all averages to the selected calculator. Missing grades skip a student
    and soft-delete their prior active result for that term rather than treat missing
    as zero. Reuse existing result rows and retire duplicates. Return calculated
    results, skipped-student details, and invalidated rows without committing.
    """
    results: list[CourseResult] = []
    skipped_students: list[SkippedCourseResultStudent] = []
    invalidated_results: list[CourseResult] = []

    if beninese:
        interro_items = [item for item in grade_items if item.item_type == "INTERRO"]
        devoir_item = next((item for item in grade_items if item.item_type == "DEVOIR"), None)
        composition_item = next((item for item in grade_items if item.item_type == "COMPOSITION"), None)

    for student in students:
        grades = db.scalars(
            select(Grade)
            .join(GradeItem, Grade.grade_item_id == GradeItem.id)
            .where(
                Grade.student_id == student.id,
                GradeItem.course_id == course.id,
                Grade.deleted_at.is_(None),
                GradeItem.deleted_at.is_(None),
            )
        ).all()
        grades_by_item_id = {grade.grade_item_id: grade for grade in grades}
        missing_grade_items = [item for item in grade_items if item.id not in grades_by_item_id]

        # Missing is not zero. Keeping an earlier CourseResult here would make
        # it disagree with current grades and could leak a stale average into a
        # newly generated bulletin, so incomplete input invalidates the result.
        if missing_grade_items:
            existing_results = get_term_equivalent_course_results(
                db,
                student_id=student.id,
                course_id=course.id,
                term=term,
                active_only=True,
            )
            for existing_result in existing_results:
                existing_result.deleted_at = datetime.now(timezone.utc)
                invalidated_results.append(existing_result)
            skipped_students.append(
                SkippedCourseResultStudent(
                    student_id=student.id,
                    student_name=f"{student.first_name} {student.last_name}",
                    missing_grade_items=[item.title for item in missing_grade_items],
                )
            )
            continue

        if beninese:
            interros = [
                {"score": grades_by_item_id[item.id].score, "max_score": item.max_score}
                for item in interro_items
            ]
            devoir = {"score": grades_by_item_id[devoir_item.id].score, "max_score": devoir_item.max_score}
            composition = {
                "score": grades_by_item_id[composition_item.id].score,
                "max_score": composition_item.max_score,
            }
            try:
                average, moy_int, mcc = calculate_beninese_average(interros, devoir, composition)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            devoir_score = round(devoir["score"] / devoir["max_score"] * 20, 2)
            composition_score = round(composition["score"] / composition["max_score"] * 20, 2)
        else:
            grade_data = [
                {
                    "score": grades_by_item_id[item.id].score,
                    "max_score": item.max_score,
                    "weight": item.weight,
                }
                for item in grade_items
            ]
            try:
                average = calculate_course_average(grade_data)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            moy_int = None
            mcc = None
            devoir_score = None
            composition_score = None

        letter_grade = get_letter_grade(average)
        calculated_at = datetime.now(timezone.utc)
        course_result = get_course_result_for_recalculation(
            db,
            student_id=student.id,
            course=course,
            term=term,
        )

        if course_result is None:
            course_result = CourseResult(
                student_id=student.id,
                course_id=course.id,
                term=term,
                average=average,
                letter_grade=letter_grade,
                scale="20",
                calculated_at=calculated_at,
                moy_int=moy_int,
                mcc=mcc,
                devoir_score=devoir_score,
                composition_score=composition_score,
            )
            db.add(course_result)
        else:
            for duplicate_result in get_term_equivalent_course_results(
                db,
                student_id=student.id,
                course_id=course.id,
                term=term,
                active_only=True,
            ):
                if duplicate_result.id != course_result.id:
                    duplicate_result.deleted_at = calculated_at
            course_result.term = term
            course_result.average = average
            course_result.letter_grade = letter_grade
            # Recalculated averages are always on the /20 scale, even if this
            # row was previously a historical /100 result.
            course_result.scale = "20"
            course_result.calculated_at = calculated_at
            course_result.deleted_at = None
            course_result.moy_int = moy_int
            course_result.mcc = mcc
            course_result.devoir_score = devoir_score
            course_result.composition_score = composition_score

        results.append(course_result)

    return results, skipped_students, invalidated_results


@router.post("/course-results/calculate/{course_id}", response_model=CourseResultCalculationResponse)
def calculate_course_results(
    course_id: UUID,
    term: TrimesterTerm | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResultCalculationResponse:
    """Authorize an admin/assigned teacher, calculate all enrolled students, audit, and commit.

    Use the explicit term when provided or course.term otherwise. Return results
    and skip/invalidation counts; parents cannot invoke this calculation.
    """
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    calculation_term = term.value if term is not None else course.term
    grade_items = get_course_grade_items(db, course, calculation_term)
    students = get_enrolled_students_for_course(db, course)
    beninese = is_beninese_mode(course)
    results, skipped_students, invalidated_results = calculate_results_for_students(
        db,
        course=course,
        grade_items=grade_items,
        students=students,
        term=calculation_term,
        beninese=beninese,
    )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_results_calculated",
        entity_type="course",
        entity_id=course.id,
        new_value={
            "course_id": course.id,
            "term": calculation_term,
            "calculated_count": len(results),
            "skipped_students_count": len(skipped_students),
            "invalidated_count": len(invalidated_results),
        },
    )
    db.commit()
    for result in results:
        db.refresh(result)

    return CourseResultCalculationResponse(
        course_id=course.id,
        term=calculation_term,
        calculated_count=len(results),
        invalidated_count=len(invalidated_results),
        skipped_students=skipped_students,
        results=[to_course_result_response(result) for result in results],
    )


@router.post("/course-results/calculate/{course_id}/students", response_model=CourseResultCalculationResponse)
def calculate_selected_course_results(
    course_id: UUID,
    payload: CourseResultCalculationRequest,
    term: TrimesterTerm | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResultCalculationResponse:
    """Calculate and commit results only for the requested enrolled students and term.

    Require admin or course ownership, audit counts, and return calculated/skipped
    results. Restricting the selection avoids touching unrelated students' reports.
    """
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    calculation_term = term.value if term is not None else course.term
    grade_items = get_course_grade_items(db, course, calculation_term)
    students = get_selected_enrolled_students(db, course, payload.student_ids)
    beninese = is_beninese_mode(course)
    results, skipped_students, invalidated_results = calculate_results_for_students(
        db,
        course=course,
        grade_items=grade_items,
        students=students,
        term=calculation_term,
        beninese=beninese,
    )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_results_calculated",
        entity_type="course",
        entity_id=course.id,
        new_value={
            "course_id": course.id,
            "term": calculation_term,
            "calculated_count": len(results),
            "skipped_students_count": len(skipped_students),
            "invalidated_count": len(invalidated_results),
            "requested_student_count": len(dict.fromkeys(payload.student_ids)),
        },
    )
    db.commit()
    for result in results:
        db.refresh(result)

    return CourseResultCalculationResponse(
        course_id=course.id,
        term=calculation_term,
        calculated_count=len(results),
        invalidated_count=len(invalidated_results),
        skipped_students=skipped_students,
        results=[to_course_result_response(result) for result in results],
    )


@router.get("/course-results/student/{student_id}", response_model=list[CourseResultResponse])
def list_student_course_results(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResultResponse]:
    """Return active results for a student after checking the caller's scope.

    Admins see all; teachers need an active enrollment in their courses and receive
    only their own course results. Parents are denied.
    """
    get_student_or_404(db, student_id)

    if current_user.role == "admin":
        course_results = db.scalars(
            select(CourseResult)
            .where(CourseResult.student_id == student_id, CourseResult.deleted_at.is_(None))
            .order_by(CourseResult.term)
        ).all()
        return [to_course_result_response(course_result) for course_result in course_results]

    if current_user.role == "teacher":
        teacher_course_ids = get_teacher_course_ids(db, current_user)
        if not teacher_course_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        is_enrolled_in_teacher_course = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id.in_(teacher_course_ids),
                Enrollment.deleted_at.is_(None),
            )
        )
        if is_enrolled_in_teacher_course is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        course_results = db.scalars(
            select(CourseResult)
            .where(
                CourseResult.student_id == student_id,
                CourseResult.course_id.in_(teacher_course_ids),
                CourseResult.deleted_at.is_(None),
            )
            .order_by(CourseResult.term)
        ).all()
        return [to_course_result_response(course_result) for course_result in course_results]

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("/course-results/{course_id}", response_model=list[CourseResultResponse])
def list_course_results(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResultResponse]:
    """Return stored course results to an admin or its assigned teacher.

    Exclude deleted results/students, retain graduated history, and reject parents.
    """
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    course_results = db.scalars(
        select(CourseResult)
        .join(Student, CourseResult.student_id == Student.id)
        .where(
            CourseResult.course_id == course.id,
            CourseResult.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
        .order_by(CourseResult.term, CourseResult.student_id)
    ).all()
    return [to_course_result_response(course_result) for course_result in course_results]
