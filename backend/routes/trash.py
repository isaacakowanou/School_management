"""Admin API for the unified Corbeille and its irreversible purge actions.

Every endpoint first performs the lazy 30-day retention sweep; listing returns both
batch and standalone entries from ``services.trash``. ``entity_type`` is a
filtered view of that same source, which keeps per-entity deleted pages aligned
with the main bin. Restore reactivates retained entries; DELETE endpoints
perform audited hard deletes with no recovery path. Retention can commit
expired-entry deletion before the requested operation succeeds or fails.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import require_admin
from database import get_db
from models import User
from schemas import StatusResponse, TrashActionResponse, TrashEntryResponse, TrashListResponse
from services.trash import (
    RETENTION_DAYS,
    list_trash_entries,
    parse_entry_id,
    purge_all_entries,
    purge_entry,
    purge_expired_entries,
    restore_batch_entry,
    restore_row_entry,
    trash_summary,
)

router = APIRouter(prefix="/admin/trash", tags=["trash"])


def _entry_response(entry) -> TrashEntryResponse:
    """Serialize a Trash entry, replacing missing display metadata with an empty mapping."""
    return TrashEntryResponse(
        id=entry.id,
        source=entry.source,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        target_label=entry.target_label,
        deleted_at=entry.deleted_at,
        counts=entry.counts,
        metadata=entry.metadata or {},
        restored_at=entry.restored_at,
    )


def _auto_purge(db: Session, current_user: User) -> None:
    # BackgroundTasks cannot schedule daily work after a process sleeps or
    # restarts, so access-triggered cleanup is the reliable scheduler-free path.
    """Sweep expired entries for the requesting admin and commit when deletion counts are nonempty.

    Service failures propagate to the route. A successful nonempty sweep commits
    before the requested list, restore, or purge action is attempted.
    """
    counts = purge_expired_entries(db, current_user=current_user)
    if counts:
        db.commit()


@router.get("", response_model=TrashListResponse)
def list_trash(
    entity_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrashListResponse:
    """Return admin-visible Trash entries, summary counts, and retention days.

    Run retention cleanup across all entity types first, then apply the optional
    entity_type filter to both entries and summary. This GET can permanently
    delete expired data and commit those changes.
    """
    _auto_purge(db, current_user)
    entries = list_trash_entries(db, entity_type=entity_type)
    return TrashListResponse(
        entries=[_entry_response(entry) for entry in entries],
        summary=trash_summary(entries),
        retention_days=RETENTION_DAYS,
    )


@router.post("/{entry_id}/restore", response_model=StatusResponse)
def restore_trash_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    """Restore a prefixed row or batch id for an admin, commit, and return its label.

    Retention cleanup runs first, so an expired target may already be gone.
    Malformed ids become HTTP 404; dependency and identity conflicts from the
    shared restore service propagate. Successful restore is audited there.
    """
    _auto_purge(db, current_user)
    try:
        source, table, entity_id = parse_entry_id(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found") from exc

    if source == "batch":
        label, _ = restore_batch_entry(db, batch_id=entity_id, current_user=current_user)
    else:
        assert table is not None
        label = restore_row_entry(db, table=table, entity_id=entity_id, current_user=current_user)
    db.commit()
    return StatusResponse(status="ok", message=f"{label} restored")


@router.delete("/{entry_id}", response_model=TrashActionResponse)
def purge_trash_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrashActionResponse:
    """Permanently purge an admin-selected entry, commit, and return its label and counts.

    Run retention first, then delegate ownership closure, actor protection,
    savepoint handling, and audit to the service. Missing targets raise HTTP 404,
    including those removed by the preceding retention sweep.
    """
    _auto_purge(db, current_user)
    label, counts = purge_entry(db, entry_id=entry_id, current_user=current_user)
    db.commit()
    return TrashActionResponse(status="ok", message="Trash entry permanently deleted", target_label=label, counts=counts)


@router.delete("", response_model=TrashActionResponse)
def empty_trash(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrashActionResponse:
    """Purge all remaining entries for an admin, audit the overall action, and commit.

    Return counts from the explicit empty operation; counts from the preceding
    retention sweep are not included. Service errors propagate rather than
    being reported as a successful empty operation.
    """
    _auto_purge(db, current_user)
    counts = purge_all_entries(db, current_user=current_user)
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="trash_emptied",
        entity_type="trash",
        entity_id=current_user.id,
        old_value=None,
        new_value={"counts": counts},
    )
    db.commit()
    return TrashActionResponse(status="ok", message="Trash emptied", counts=counts)
