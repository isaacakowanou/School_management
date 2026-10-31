"""Stage audit records alongside the actions they describe.

Normalize UUIDs and dates for JSON storage and leave the commit to callers so
record changes and their audits can share a transaction. Nullable actors support
failed login and other events where identity is not proven; this helper does
not invent a user or enforce permissions.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from models import AuditLog


def _json_safe(value):
    """Recursively convert UUIDs and dates in audit values to JSON-safe strings."""
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
    """Add an audit row to the session and return it, without committing.

    Record the actor, action, target, and optional before/after dictionaries;
    convert UUIDs and dates to JSON-safe strings. A null actor supports events
    without a proven identity. The caller commits the row with its domain change.
    """
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
