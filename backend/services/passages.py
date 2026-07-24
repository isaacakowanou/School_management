"""Year-end class passage triage and year-scoped assignment rules.

Passage de classe records source/target assignments by school year and also
updates the temporary live ``Student.class_id`` pointer or marks Terminale
students as graduated. It does not create courses, enrollments, or Trash rows.
Target-year Class rows are ordinary per-year records; admins create them today
with Classes -> Create GGFK classes for the target school year before applying
passage decisions.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import create_audit_log
from constants import (
    PASSAGE_LADDER,
    PASSAGE_PASS_THRESHOLD,
    PASSAGE_REPEAT_THRESHOLD,
    TERMINALE_CLASSES,
    normalize_class_name,
)
from models import AuditLog, Class, Student, StudentClassAssignment, StudentPassageDecision, User
from services.annual_averages import AnnualAverages, compute_student_annual_averages
from services.student_assignments import assignment_for_student_year, set_student_assignment


PASSAGE_DECISION_PASS = "pass"
PASSAGE_DECISION_REPEAT = "repeat"
PASSAGE_DECISION_GRADUATE = "graduate"
PASSAGE_DECISION_DELIBERATION = "deliberation"


@dataclass(frozen=True)
class PassageSuggestion:
    decision: str
    requires_decision: bool
    reason: str


def suggest_passage_decision(annual: AnnualAverages) -> PassageSuggestion:
    considered = [value for value in (annual.french, annual.english) if value is not None]
    if not considered:
        considered = [annual.bilingual] if annual.bilingual is not None else []
    if annual.incomplete or not considered:
        return PassageSuggestion(PASSAGE_DECISION_DELIBERATION, True, "Données incomplètes")
    if all(value >= PASSAGE_PASS_THRESHOLD for value in considered):
        return PassageSuggestion(PASSAGE_DECISION_PASS, False, "Moyenne annuelle >= 10")
    if any(value < PASSAGE_REPEAT_THRESHOLD for value in considered):
        return PassageSuggestion(PASSAGE_DECISION_REPEAT, False, "Moyenne annuelle < 9")
    return PassageSuggestion(PASSAGE_DECISION_DELIBERATION, True, "Zone de délibération")


def next_class_names(class_name: str | None) -> list[str]:
    if not class_name:
        return []
    normalized = normalize_class_name(class_name)
    for source_name, targets in PASSAGE_LADDER.items():
        if normalize_class_name(source_name) == normalized:
            return targets
    return []


def is_terminale(class_name: str | None) -> bool:
    if not class_name:
        return False
    return normalize_class_name(class_name) in {normalize_class_name(name) for name in TERMINALE_CLASSES}


def target_classes_by_name(db: Session, target_school_year: str) -> dict[str, Class]:
    classes = db.scalars(
        select(Class).where(Class.school_year == target_school_year, Class.deleted_at.is_(None))
    ).all()
    return {normalize_class_name(school_class.name_fr): school_class for school_class in classes}


def find_target_class(db: Session, target_school_year: str, target_class_name: str | None) -> Class | None:
    if target_class_name is None:
        return None
    return target_classes_by_name(db, target_school_year).get(normalize_class_name(target_class_name))


def decision_for_student_year(db: Session, student_id: UUID, school_year: str) -> StudentPassageDecision | None:
    return db.scalar(
        select(StudentPassageDecision).where(
            StudentPassageDecision.student_id == student_id,
            StudentPassageDecision.school_year == school_year,
        )
    )


def _active_student_query():
    return select(Student).where(
        Student.deleted_at.is_(None),
        Student.academic_status == "active",
    )


def students_for_passage_class(db: Session, class_id: UUID, school_year: str) -> list[Student]:
    assigned_student_ids = db.scalars(
        select(StudentClassAssignment.student_id).where(
            StudentClassAssignment.class_id == class_id,
            StudentClassAssignment.school_year == school_year,
        )
    ).all()
    existing_decision_student_ids = db.scalars(
        select(StudentPassageDecision.student_id).where(
            StudentPassageDecision.from_class_id == class_id,
            StudentPassageDecision.school_year == school_year,
        )
    ).all()
    conditions = [Student.id.in_(assigned_student_ids)] if assigned_student_ids else []
    if existing_decision_student_ids:
        conditions.append(Student.id.in_(existing_decision_student_ids))
    from sqlalchemy import or_

    if not conditions:
        return []
    return list(
        db.scalars(
            _active_student_query()
            .where(or_(*conditions))
            .order_by(Student.last_name, Student.first_name, Student.student_number)
        ).all()
    )


def all_students_for_passage_year(db: Session, school_year: str) -> list[Student]:
    return list(
        db.scalars(
            _active_student_query()
            .join(StudentClassAssignment, StudentClassAssignment.student_id == Student.id)
            .where(StudentClassAssignment.school_year == school_year)
            .order_by(Student.last_name, Student.first_name, Student.student_number)
        ).all()
    )


def target_class_requirement(
    student: Student,
    final_decision: str,
    requested_target_class_name: str | None,
    *,
    source_class_name: str | None = None,
) -> tuple[Class | None, str | None]:
    class_name = source_class_name or (student.school_class.name_fr if student.school_class else None)
    if final_decision == PASSAGE_DECISION_REPEAT:
        return None, class_name
    if final_decision == PASSAGE_DECISION_GRADUATE:
        return None, "Diplômé"
    if final_decision != PASSAGE_DECISION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_decision_required", "message": "Decision is required"})
    targets = next_class_names(class_name)
    if is_terminale(class_name):
        return None, "Diplômé"
    if not targets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_ladder_missing", "message": "No next class is configured"})
    target_name = requested_target_class_name or (targets[0] if len(targets) == 1 else None)
    if target_name is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_stream_required", "message": "Choose 1ère C or 1ère D for 2nde students"})
    if normalize_class_name(target_name) not in {normalize_class_name(name) for name in targets}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_invalid_target_class", "message": "Target class is not valid for this student"})
    return None, target_name


def ensure_target_year_class_exists(
    db: Session,
    target_school_year: str,
    target_class_name: str | None,
) -> Class | None:
    if target_class_name in (None, "Diplômé"):
        return None
    target_class = find_target_class(db, target_school_year, target_class_name)
    if target_class is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "target_class_missing",
                "message": f"Create class {target_class_name} for {target_school_year} before applying passage.",
                "target_school_year": target_school_year,
                "missing_class": target_class_name,
            },
        )
    return target_class


def assert_existing_decision_can_be_edited(db: Session, decision: StudentPassageDecision) -> None:
    later_activity = db.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_type.in_(["grade", "course_result", "report_card"]),
            AuditLog.created_at > decision.decided_at,
        ).limit(1)
    )
    if later_activity is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "passage_decision_locked_by_later_activity", "message": "This passage decision already has later academic activity."},
        )


def apply_passage_decision(
    db: Session,
    *,
    student: Student,
    annual: AnnualAverages,
    suggested: PassageSuggestion,
    school_year: str,
    target_school_year: str,
    final_decision: str,
    target_class_name: str | None,
    note: str | None,
    current_user: User,
) -> StudentPassageDecision:
    existing = decision_for_student_year(db, student.id, school_year)
    if existing is not None:
        assert_existing_decision_can_be_edited(db, existing)

    source_assignment = assignment_for_student_year(db, student.id, school_year)
    existing_source_class_name = existing.from_class_name if existing is not None else None
    source_class_name = existing_source_class_name or (
        source_assignment.class_name_snapshot if source_assignment is not None else None
    )
    _, required_target_name = target_class_requirement(
        student,
        final_decision,
        target_class_name,
        source_class_name=source_class_name,
    )
    if final_decision == PASSAGE_DECISION_PASS and is_terminale(source_class_name):
        final_decision = PASSAGE_DECISION_GRADUATE
        required_target_name = "Diplômé"

    target_class = ensure_target_year_class_exists(db, target_school_year, required_target_name)
    now = datetime.now(timezone.utc)
    old_value = None
    if existing is not None:
        old_value = {
            "final_decision": existing.final_decision,
            "result_class_id": existing.result_class_id,
            "result_class_name": existing.result_class_name,
            "note": existing.note,
        }
        decision = existing
    else:
        decision = StudentPassageDecision(student=student, school_year=school_year, target_school_year=target_school_year)
        db.add(decision)

    source_class = (
        existing.from_class
        if existing is not None and existing.from_class is not None
        else source_assignment.school_class if source_assignment is not None else None
    )
    decision.from_class = source_class
    decision.from_class_name = source_class.name_fr if source_class else None
    decision.result_class = target_class
    decision.result_class_name = required_target_name
    decision.suggested_decision = suggested.decision
    decision.final_decision = final_decision
    decision.annual_french_average = annual.french
    decision.annual_english_average = annual.english
    decision.annual_bilingual_average = annual.bilingual
    decision.incomplete_data = annual.incomplete
    decision.note = note.strip() if note else None
    decision.decided_by_admin_id = current_user.id
    decision.decided_at = now

    if final_decision == PASSAGE_DECISION_REPEAT:
        student.class_id = target_class.id if target_class else None
        if target_class is not None:
            set_student_assignment(db, student, target_class)
        student.academic_status = "active"
        student.graduated_at = None
    elif final_decision == PASSAGE_DECISION_GRADUATE:
        if source_class is not None:
            set_student_assignment(db, student, source_class)
        student.class_id = None
        student.academic_status = "graduated"
        student.graduated_at = now
    else:
        student.class_id = target_class.id if target_class else None
        if target_class is not None:
            set_student_assignment(db, student, target_class)
        student.academic_status = "active"
        student.graduated_at = None

    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_passage_decided",
        entity_type="student_passage_decision",
        entity_id=decision.id,
        old_value=old_value,
        new_value={
            "student_id": student.id,
            "school_year": school_year,
            "target_school_year": target_school_year,
            "final_decision": final_decision,
            "result_class_id": decision.result_class_id,
            "result_class_name": decision.result_class_name,
            "annual_french_average": annual.french,
            "annual_english_average": annual.english,
            "annual_bilingual_average": annual.bilingual,
        },
    )
    return decision


def annual_for_student(db: Session, student: Student, school_year: str) -> tuple[AnnualAverages, PassageSuggestion]:
    annual = compute_student_annual_averages(db, student.id, school_year)
    return annual, suggest_passage_decision(annual)
