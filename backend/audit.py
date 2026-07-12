"""Append-only construction helper for operational and authentication audit rows.

Callers own transaction boundaries so an audit row commits atomically with the
action it describes. Values are normalized to JSON-safe UUID/date strings.
``actor_user_id`` may be null for security events where no identity is proven,
notably failed login and anti-enumeration reset requests; see the auth module for
why those events must not manufacture or disclose an actor.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from models import AuditLog


def _json_safe(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def create_audit_log(
    db: Session,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=_json_safe(old_value),
        new_value=_json_safe(new_value),
    )
    db.add(audit_log)
    return audit_log
