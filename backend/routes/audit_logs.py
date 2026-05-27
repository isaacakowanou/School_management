from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import AuditLog, User
from schemas import AuditLogResponse


router = APIRouter(tags=["audit logs"])


def to_audit_log_response(audit_log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=audit_log.id,
        actor_user_id=audit_log.actor_user_id,
        action=audit_log.action,
        entity_type=audit_log.entity_type,
        entity_id=audit_log.entity_id,
        old_value=audit_log.old_value,
        new_value=audit_log.new_value,
        created_at=audit_log.created_at,
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AuditLogResponse]:
    query = select(AuditLog)

    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if actor_user_id is not None:
        query = query.where(AuditLog.actor_user_id == actor_user_id)

    audit_logs = db.scalars(query.order_by(AuditLog.created_at.desc())).all()
    return [to_audit_log_response(audit_log) for audit_log in audit_logs]
