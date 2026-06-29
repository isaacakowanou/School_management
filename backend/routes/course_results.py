from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from audit import create_audit_log
from database import get_db
from models import Course, CourseResult, Enrollment, Grade, GradeItem, Student, User
from schemas import (
    CourseResultCalculationRequest,
    CourseResultCalculationResponse,
    CourseResultResponse,
    SkippedCourseResultStudent,
)
from services.grade_calculator import calculate_course_average, letter_grade_for_course_average
from utils import get_current_teacher


router = APIRouter(tags=["course results"])


def to_course_result_response(course_result: CourseResult) -> CourseResultResponse:
    return CourseResultResponse(
        id=course_result.id,
        student_id=course_result.student_id,
        course_id=course_result.course_id,
        term=course_result.term,
        average=course_result.average,
        letter_grade=course_result.letter_grade,
        scale=course_result.scale,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def can_access_course_results(db: Session, current_user: User, course: Course) -> bool:
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def get_teacher_course_ids(db: Session, current_user: User) -> list[UUID]:
    teacher = get_current_teacher(db, current_user)
    if teacher is None:
        return []

    return list(db.scalars(select(Course.id).where(Course.teacher_id == teacher.id)).all())


def validate_course_grade_items(grade_items: list[GradeItem]) -> None:
    if not grade_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course has no grade items")

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


def get_course_grade_items(db: Session, course: Course) -> list[GradeItem]:
    grade_items = db.scalars(
        select(GradeItem).where(GradeItem.course_id == course.id).order_by(GradeItem.created_at)
    ).all()
    validate_course_grade_items(list(grade_items))
    return list(grade_items)


def get_enrolled_students_for_course(db: Session, course: Course) -> list[Student]:
    return list(
        db.scalars(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == course.id)
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def get_selected_enrolled_students(db: Session, course: Course, student_ids: list[UUID]) -> list[Student]:
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
) -> tuple[list[CourseResult], list[SkippedCourseResultStudent]]:
    results: list[CourseResult] = []
    skipped_students: list[SkippedCourseResultStudent] = []

    for student in students:
        grades = db.scalars(
            select(Grade)
            .join(GradeItem, Grade.grade_item_id == GradeItem.id)
            .where(
                Grade.student_id == student.id,
                GradeItem.course_id == course.id,
            )
        ).all()
        grades_by_item_id = {grade.grade_item_id: grade for grade in grades}
        missing_grade_items = [item for item in grade_items if item.id not in grades_by_item_id]

        if missing_grade_items:
            skipped_students.append(
                SkippedCourseResultStudent(
                    student_id=student.id,
                    student_name=f"{student.first_name} {student.last_name}",
                    missing_grade_items=[item.title for item in missing_grade_items],
                )
            )
            continue

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

        letter_grade = letter_grade_for_course_average(average)
        calculated_at = datetime.now(timezone.utc)
        course_result = db.scalar(
            select(CourseResult).where(
                CourseResult.student_id == student.id,
                CourseResult.course_id == course.id,
                CourseResult.term == course.term,
            )
        )

        if course_result is None:
            course_result = CourseResult(
                student_id=student.id,
                course_id=course.id,
                term=course.term,
                average=average,
                letter_grade=letter_grade,
                scale="20",
                calculated_at=calculated_at,
            )
            db.add(course_result)
        else:
            course_result.average = average
            course_result.letter_grade = letter_grade
            # Recalculated averages are always on the /20 scale, even if this
            # row was previously a historical /100 result.
            course_result.scale = "20"
            course_result.calculated_at = calculated_at

        results.append(course_result)

    return results, skipped_students


@router.post("/course-results/calculate/{course_id}", response_model=CourseResultCalculationResponse)
def calculate_course_results(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResultCalculationResponse:
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    grade_items = get_course_grade_items(db, course)
    students = get_enrolled_students_for_course(db, course)
    results, skipped_students = calculate_results_for_students(
        db,
        course=course,
        grade_items=grade_items,
        students=students,
    )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_results_calculated",
        entity_type="course",
        entity_id=course.id,
        new_value={
            "course_id": course.id,
            "calculated_count": len(results),
            "skipped_students_count": len(skipped_students),
        },
    )
    db.commit()
    for result in results:
        db.refresh(result)

    return CourseResultCalculationResponse(
        course_id=course.id,
        term=course.term,
        calculated_count=len(results),
        skipped_students=skipped_students,
        results=[to_course_result_response(result) for result in results],
    )


@router.post("/course-results/calculate/{course_id}/students", response_model=CourseResultCalculationResponse)
def calculate_selected_course_results(
    course_id: UUID,
    payload: CourseResultCalculationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResultCalculationResponse:
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    grade_items = get_course_grade_items(db, course)
    students = get_selected_enrolled_students(db, course, payload.student_ids)
    results, skipped_students = calculate_results_for_students(
        db,
        course=course,
        grade_items=grade_items,
        students=students,
    )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_results_calculated",
        entity_type="course",
        entity_id=course.id,
        new_value={
            "course_id": course.id,
            "calculated_count": len(results),
            "skipped_students_count": len(skipped_students),
            "requested_student_count": len(dict.fromkeys(payload.student_ids)),
        },
    )
    db.commit()
    for result in results:
        db.refresh(result)

    return CourseResultCalculationResponse(
        course_id=course.id,
        term=course.term,
        calculated_count=len(results),
        skipped_students=skipped_students,
        results=[to_course_result_response(result) for result in results],
    )


@router.get("/course-results/student/{student_id}", response_model=list[CourseResultResponse])
def list_student_course_results(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResultResponse]:
    get_student_or_404(db, student_id)

    if current_user.role == "admin":
        course_results = db.scalars(
            select(CourseResult).where(CourseResult.student_id == student_id).order_by(CourseResult.term)
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
            )
        )
        if is_enrolled_in_teacher_course is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        course_results = db.scalars(
            select(CourseResult)
            .where(
                CourseResult.student_id == student_id,
                CourseResult.course_id.in_(teacher_course_ids),
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
    course = get_course_or_404(db, course_id)
    if not can_access_course_results(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    course_results = db.scalars(
        select(CourseResult)
        .where(CourseResult.course_id == course.id)
        .order_by(CourseResult.term, CourseResult.student_id)
    ).all()
    return [to_course_result_response(course_result) for course_result in course_results]
