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
    counts = purge_expired_entries(db, current_user=current_user)
    if counts:
        db.commit()


@router.get("", response_model=TrashListResponse)
def list_trash(
    entity_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrashListResponse:
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
    _auto_purge(db, current_user)
    label, counts = purge_entry(db, entry_id=entry_id, current_user=current_user)
    db.commit()
    return TrashActionResponse(status="ok", message="Trash entry permanently deleted", target_label=label, counts=counts)


@router.delete("", response_model=TrashActionResponse)
def empty_trash(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrashActionResponse:
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
