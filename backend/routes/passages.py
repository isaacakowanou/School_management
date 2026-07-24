"""Admin Passage de classe preview, decision, and history endpoints.

Classes are per school year in this app. The target year therefore needs its
own Class rows before a student can be moved there; admins create them from the
Classes page, either manually or with the GGFK bulk-create button.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from auth import get_current_user, require_admin
from constants import normalize_class_name
from database import get_db
from models import Class, Parent, Student, StudentParent, StudentPassageDecision, User
from schemas import (
    PassageClassPreviewResponse,
    PassageConfirmRequest,
    PassageConfirmResponse,
    PassageDecisionResponse,
    ParentPassageDecisionResponse,
    PassageStudentRow,
)
from services.passages import (
    PASSAGE_DECISION_GRADUATE,
    PASSAGE_DECISION_PASS,
    PASSAGE_DECISION_REPEAT,
    all_students_for_passage_year,
    annual_for_student,
    apply_passage_decision,
    decision_for_student_year,
    ensure_target_year_class_exists,
    is_terminale,
    next_class_names,
    target_class_requirement,
    students_for_passage_class,
    target_classes_by_name,
)


router = APIRouter(tags=["passages"])


def _decision_response(decision: StudentPassageDecision) -> PassageDecisionResponse:
    return PassageDecisionResponse(
        id=decision.id,
        student_id=decision.student_id,
        school_year=decision.school_year,
        target_school_year=decision.target_school_year,
        from_class_id=decision.from_class_id,
        from_class_name=decision.from_class_name,
        result_class_id=decision.result_class_id,
        result_class_name=decision.result_class_name,
        suggested_decision=decision.suggested_decision,
        final_decision=decision.final_decision,
        annual_french_average=decision.annual_french_average,
        annual_english_average=decision.annual_english_average,
        annual_bilingual_average=decision.annual_bilingual_average,
        incomplete_data=decision.incomplete_data,
        note=decision.note,
        decided_by_admin_id=decision.decided_by_admin_id,
        decided_at=decision.decided_at,
    )


def _parent_decision_response(decision: StudentPassageDecision) -> ParentPassageDecisionResponse:
    return ParentPassageDecisionResponse(
        school_year=decision.school_year,
        from_class_name=decision.from_class_name,
        decision=decision.final_decision,
        result_class_name=decision.result_class_name,
    )


def _parent_can_read_student(db: Session, current_user: User, student_id: UUID) -> bool:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id, Parent.deleted_at.is_(None)))
    if parent is None:
        return False
    link = db.scalar(
        select(StudentParent)
        .join(Student, StudentParent.student_id == Student.id)
        .where(
            StudentParent.parent_id == parent.id,
            StudentParent.student_id == student_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    )
    return link is not None


def _row_for_student(db: Session, student: Student, school_year: str, target_school_year: str) -> PassageStudentRow:
    annual, suggested = annual_for_student(db, student, school_year)
    existing = decision_for_student_year(db, student.id, school_year)
    current_class_name = student.school_class.name_fr if student.school_class else None
    target_options = ["Diplômé"] if is_terminale(current_class_name) else next_class_names(current_class_name)
    targets = target_classes_by_name(db, target_school_year)
    final_decision = existing.final_decision if existing else (
        PASSAGE_DECISION_GRADUATE if suggested.decision == PASSAGE_DECISION_PASS and is_terminale(current_class_name)
        else suggested.decision if suggested.decision in (PASSAGE_DECISION_PASS, PASSAGE_DECISION_REPEAT) and not suggested.requires_decision
        else None
    )
    target_class_name = existing.result_class_name if existing else (
        "Diplômé" if final_decision == PASSAGE_DECISION_GRADUATE
        else target_options[0] if final_decision == PASSAGE_DECISION_PASS and len(target_options) == 1
        else current_class_name if final_decision == PASSAGE_DECISION_REPEAT
        else None
    )
    required_names = list(target_options)
    if target_class_name and target_class_name != "Diplômé":
        required_names.append(target_class_name)
    missing_targets = [
        name for name in required_names
        if name != "Diplômé" and normalize_class_name(name) not in targets
    ]
    return PassageStudentRow(
        student_id=student.id,
        student_name=f"{student.first_name} {student.last_name}",
        student_number=student.student_number,
        current_class_id=student.class_id,
        current_class_name=current_class_name,
        annual_french_average=annual.french,
        annual_english_average=annual.english,
        annual_bilingual_average=annual.bilingual,
        incomplete_data=annual.incomplete,
        missing_terms=annual.missing_terms,
        suggested_decision=suggested.decision,
        suggested_reason=suggested.reason,
        requires_decision=suggested.requires_decision or (final_decision == PASSAGE_DECISION_PASS and len(target_options) > 1),
        existing_decision_id=existing.id if existing else None,
        final_decision=final_decision,
        target_class_id=existing.result_class_id if existing else None,
        target_class_name=target_class_name,
        target_options=target_options,
        target_class_missing=bool(missing_targets),
        note=existing.note if existing else None,
    )


@router.get("/classes/{class_id}", response_model=PassageClassPreviewResponse)
def preview_class_passage(
    class_id: UUID,
    target_school_year: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> PassageClassPreviewResponse:
    school_class = db.get(Class, class_id)
    if school_class is None or school_class.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    students = students_for_passage_class(db, school_class.id, school_class.school_year)
    rows = [_row_for_student(db, student, school_class.school_year, target_school_year) for student in students]
    target_lookup = target_classes_by_name(db, target_school_year)
    missing_candidates = []
    for row in rows:
        missing_candidates.extend(row.target_options)
        if row.target_class_name:
            missing_candidates.append(row.target_class_name)
    missing = sorted({
        name
        for name in missing_candidates
        if name != "Diplômé" and normalize_class_name(name) not in target_lookup
    })
    return PassageClassPreviewResponse(
        class_id=school_class.id,
        class_name=school_class.name_fr,
        school_year=school_class.school_year,
        target_school_year=target_school_year,
        target_classes_ready=not missing,
        missing_target_class_names=missing,
        target_class_guidance=(
            f"Créez les classes {', '.join(missing)} pour {target_school_year} depuis Classes > Créer les classes GGFK."
            if missing else None
        ),
        students=rows,
    )


@router.post("/confirm", response_model=PassageConfirmResponse)
def confirm_passage(
    payload: PassageConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PassageConfirmResponse:
    if not payload.decisions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_decision_required", "message": "At least one decision is required"})

    students_by_id = {
        student.id: student
        for student in db.scalars(
            select(Student)
            .options(joinedload(Student.school_class))
            .where(Student.id.in_([entry.student_id for entry in payload.decisions]), Student.deleted_at.is_(None))
        ).all()
    }
    if len(students_by_id) != len({entry.student_id for entry in payload.decisions}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Validate every target before mutating any student so the batch is atomic.
    prepared = []
    for entry in payload.decisions:
        student = students_by_id[entry.student_id]
        annual, suggested = annual_for_student(db, student, payload.school_year)
        final_decision = entry.final_decision.value
        existing = decision_for_student_year(db, student.id, payload.school_year)
        class_name = existing.from_class_name if existing is not None else (student.school_class.name_fr if student.school_class else None)
        if suggested.requires_decision and final_decision not in (PASSAGE_DECISION_PASS, PASSAGE_DECISION_REPEAT, PASSAGE_DECISION_GRADUATE):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "passage_decision_required", "message": "Deliberation rows require an explicit decision"})
        target_name = entry.target_class_name
        if final_decision == PASSAGE_DECISION_REPEAT:
            target_name = class_name
        if final_decision == PASSAGE_DECISION_PASS and is_terminale(class_name):
            final_decision = PASSAGE_DECISION_GRADUATE
            target_name = "Diplômé"
        if final_decision == PASSAGE_DECISION_GRADUATE:
            target_name = "Diplômé"
        target_class_requirement(student, final_decision, target_name, source_class_name=class_name)
        if target_name not in (None, "Diplômé"):
            ensure_target_year_class_exists(db, payload.target_school_year, target_name)
        prepared.append((student, annual, suggested, final_decision, target_name, entry.note))

    decisions = [
        apply_passage_decision(
            db,
            student=student,
            annual=annual,
            suggested=suggested,
            school_year=payload.school_year,
            target_school_year=payload.target_school_year,
            final_decision=final_decision,
            target_class_name=target_name,
            note=note,
            current_user=current_user,
        )
        for student, annual, suggested, final_decision, target_name, note in prepared
    ]
    db.commit()
    for decision in decisions:
        db.refresh(decision)
    return PassageConfirmResponse(
        status="ok",
        applied_count=len(decisions),
        decisions=[_decision_response(decision) for decision in decisions],
    )


@router.get("/students/{student_id}/history", response_model=list[PassageDecisionResponse])
def student_passage_history(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[PassageDecisionResponse]:
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    decisions = db.scalars(
        select(StudentPassageDecision)
        .where(StudentPassageDecision.student_id == student_id)
        .order_by(StudentPassageDecision.school_year.desc(), StudentPassageDecision.decided_at.desc())
    ).all()
    return [_decision_response(decision) for decision in decisions]


@router.get("/parents/students/{student_id}/history", response_model=list[ParentPassageDecisionResponse])
def parent_student_passage_history(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ParentPassageDecisionResponse]:
    if current_user.role != "parent" or not _parent_can_read_student(db, current_user, student_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    decisions = db.scalars(
        select(StudentPassageDecision)
        .where(StudentPassageDecision.student_id == student_id)
        .order_by(StudentPassageDecision.school_year.desc(), StudentPassageDecision.decided_at.desc())
    ).all()
    return [_parent_decision_response(decision) for decision in decisions]
