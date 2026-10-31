"""Read and maintain a student's class assignment for a particular school year.

Students remain permanent school members even without an assignment in a
selected year, and a missing assignment explicitly means unassigned there.
These helpers store class names alongside IDs and leave the live class pointer
and transaction commit to callers; class edits synchronize those stored names.
Other legacy historical lookup helpers still exist outside this module.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from models import Class, Student, StudentClassAssignment


def assignment_for_student_year(
    db: Session, student_id: UUID, school_year: str
) -> StudentClassAssignment | None:
    """Return the student's assignment for one school year, with its class loaded, or None."""
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
    """Return a student-ID-to-assignment map for the supplied students and school year.

    Missing entries mean unassigned in that year; an empty input returns an empty map.
    """
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
    """Create or update the student's assignment for the class's school year and return it.

    Store the class ID and French name together. This does not update the live
    Student.class_id pointer or commit; the calling workflow coordinates both.
    """
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
    """Delete only this student's assignment for the supplied year, without committing."""
    db.execute(
        delete(StudentClassAssignment).where(
            StudentClassAssignment.student_id == student_id,
            StudentClassAssignment.school_year == school_year,
        )
    )


def sync_class_assignment_snapshots(
    db: Session, school_class: Class
) -> None:
    """Update assignment years and name snapshots after a class changes.

    Reject a year move that would give a student two assignments in the target
    year. Changes remain in the caller's transaction; these name snapshots are
    updated here rather than treated as immutable bulletin text.
    """
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
