from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import AIWarning, User
from schemas import AIWarningResponse
from services.ai_checker import check_report_card_data


router = APIRouter(tags=["ai"])


@router.post("/check-report/{report_card_id}", response_model=list[AIWarningResponse])
def check_report_card(
    report_card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AIWarningResponse]:
    try:
        warnings = check_report_card_data(db, report_card_id)
    except ValueError as exc:
        if str(exc) == "Report card not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.execute(delete(AIWarning).where(AIWarning.report_card_id == report_card_id))
    for warning in warnings:
        db.add(
            AIWarning(
                report_card_id=report_card_id,
                warning_type=warning["warning_type"],
                message=warning["message"],
                severity=warning["severity"],
            )
        )
    db.commit()

    return [AIWarningResponse(**warning) for warning in warnings]
