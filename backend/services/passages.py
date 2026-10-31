"""Suggest and record year-end promotion, repetition, and graduation decisions.

Read annual bulletin averages for triage, but let the council override every
suggestion and require explicit decisions for incomplete or borderline records.
Applying a decision updates year-specific assignments and the live class pointer,
without creating courses/enrollments or treating graduation as deletion.
Target classes must already exist in their target year, normally through the
shared school-year create/complete flow.
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
    """Return a proposed decision and whether the council must explicitly decide.

    Use FR/EN tracks when present, otherwise bilingual. Incomplete data requires
    deliberation; all considered tracks at least 10 suggest pass, any below 9
    suggests repeat, and the remaining band requires deliberation. Constants
    control thresholds, and an admin may override these suggestions.
    """
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
    """Return allowed next class names from the ladder after normalizing the source name.

    Unknown or missing names return an empty list; multiple targets require a stream choice.
    """
    if not class_name:
        return []
    normalized = normalize_class_name(class_name)
    for source_name, targets in PASSAGE_LADDER.items():
        if normalize_class_name(source_name) == normalized:
            return targets
    return []


def is_terminale(class_name: str | None) -> bool:
    """Return whether a supplied class name normalizes to a configured Terminale class."""
    if not class_name:
        return False
    return normalize_class_name(class_name) in {normalize_class_name(name) for name in TERMINALE_CLASSES}


def target_classes_by_name(db: Session, target_school_year: str) -> dict[str, Class]:
    """Return active classes in the target year indexed by normalized French name."""
    classes = db.scalars(
        select(Class).where(Class.school_year == target_school_year, Class.deleted_at.is_(None))
    ).all()
    return {normalize_class_name(school_class.name_fr): school_class for school_class in classes}


def find_target_class(db: Session, target_school_year: str, target_class_name: str | None) -> Class | None:
    """Return the active class matching the supplied year and name, or None."""
    if target_class_name is None:
        return None
    return target_classes_by_name(db, target_school_year).get(normalize_class_name(target_class_name))


def decision_for_student_year(db: Session, student_id: UUID, school_year: str) -> StudentPassageDecision | None:
    """Return the student's recorded passage decision for the source year, or None."""
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
    """Return active, non-deleted students assigned to this class/year or recorded as leaving it.

    Existing decisions keep promoted students in the review set; graduated students
    are excluded by the active-student query.
    """
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
    """Return active, non-deleted students with an assignment in the requested year."""
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
    """Validate the final decision and return (None, required target name).

    Prefer the supplied source class label, falling back to the student's live
    class when absent. Repeat keeps its level, Terminale pass means graduation,
    and a branched ladder requires an explicit valid stream. Invalid choices
    raise an HTTP error; this function does not load the target class.
    """
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
    """Return the required active target-year class or raise a descriptive 409.

    No class is needed for a null target or graduation. Create/complete the school
    year beforehand; this helper does not create classes.
    """
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
    """Raise 409 if any later grade/result/report audit entry exists after this decision.

    The current query is school-wide, not limited to this student's activity.
    """
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
    """Stage a student's final passage decision, assignments, status, and audit entry.

    Use the supplied annual data and council choice, updating the existing source-year
    decision when allowed rather than promoting twice. Require a target-year class
    for pass/repeat; graduation preserves source assignment and clears the live
    class pointer without deleting history. Flush to obtain the decision ID, return
    the decision, and leave commit to the caller.
    """
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
    """Return the student's annual averages and rule-based suggestion for the supplied year."""
    annual = compute_student_annual_averages(db, student.id, school_year)
    return annual, suggest_passage_decision(annual)
