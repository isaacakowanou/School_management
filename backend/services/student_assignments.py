"""Own year-scoped student class assignments without scoping student identity.

Students are permanent school members. ``StudentClassAssignment`` is the sole
authority for year-specific class reads; ``Student.class_id`` is maintained only
as a temporary live compatibility pointer. Missing assignment rows mean the
student is explicitly unassigned for that year.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from models import Class, Student, StudentClassAssignment


def assignment_for_student_year(
    db: Session, student_id: UUID, school_year: str
) -> StudentClassAssignment | None:
    return db.scalar(
        select(StudentClassAssignment)
        .options(joinedload(StudentClassAssignment.school_class))
        .where(
            StudentClassAssignment.student_id == student_id,
            StudentClassAssignment.school_year == school_year,
        )
    )


def assignments_for_students(
    db: Session, student_ids: list[UUID], school_year: str
) -> dict[UUID, StudentClassAssignment]:
    if not student_ids:
        return {}
    rows = db.scalars(
        select(StudentClassAssignment)
        .options(joinedload(StudentClassAssignment.school_class))
        .where(
            StudentClassAssignment.student_id.in_(student_ids),
            StudentClassAssignment.school_year == school_year,
        )
    ).all()
    return {row.student_id: row for row in rows}


def set_student_assignment(
    db: Session, student: Student, school_class: Class
) -> StudentClassAssignment:
    assignment = db.scalar(
        select(StudentClassAssignment).where(
            StudentClassAssignment.student_id == student.id,
            StudentClassAssignment.school_year == school_class.school_year,
        )
    )
    if assignment is None:
        assignment = StudentClassAssignment(
            student_id=student.id,
            school_year=school_class.school_year,
            class_id=school_class.id,
            class_name_snapshot=school_class.name_fr,
        )
        db.add(assignment)
    else:
        assignment.class_id = school_class.id
        assignment.class_name_snapshot = school_class.name_fr
    return assignment


def clear_student_assignment(db: Session, student_id: UUID, school_year: str) -> None:
    db.execute(
        delete(StudentClassAssignment).where(
            StudentClassAssignment.student_id == student_id,
            StudentClassAssignment.school_year == school_year,
        )
    )


def sync_class_assignment_snapshots(
    db: Session, school_class: Class
) -> None:
    rows = db.scalars(
        select(StudentClassAssignment).where(StudentClassAssignment.class_id == school_class.id)
    ).all()
    for row in rows:
        if row.school_year != school_class.school_year:
            conflict = db.scalar(
                select(StudentClassAssignment).where(
                    StudentClassAssignment.student_id == row.student_id,
                    StudentClassAssignment.school_year == school_class.school_year,
                    StudentClassAssignment.id != row.id,
                )
            )
            if conflict is not None:
                raise ValueError("Student already has a class assignment for the target school year")
            row.school_year = school_class.school_year
        row.class_name_snapshot = school_class.name_fr
