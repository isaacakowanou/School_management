"""Admin-only XLSX preview and synchronous parent-link import endpoints."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import User
from schemas import ParentLinkImportCommitResponse, ParentLinkImportPreviewResponse
from services.import_common import ImportFileError
from services.parent_link_import import build_parent_link_import_preview, commit_parent_link_import


router = APIRouter(tags=["parents"])
MAX_FILE_BYTES = 5 * 1024 * 1024


def _raise_file_error(exc: ImportFileError) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


async def _read_xlsx(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "parent_link_import_invalid_file_type", "message": "Upload an .xlsx workbook."},
        )
    contents = await file.read(MAX_FILE_BYTES + 1)
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "parent_link_import_file_too_large", "message": "The workbook exceeds 5 MB."},
        )
    return contents


def _selected_rows(value: str) -> set[int]:
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, list) or any(not isinstance(item, int) for item in parsed):
            raise ValueError
        return set(parsed)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "parent_link_import_invalid_selection",
                "message": "Selected rows must be a JSON list of row numbers.",
            },
        ) from exc


@router.post("/preview", response_model=ParentLinkImportPreviewResponse)
async def preview_parent_link_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ParentLinkImportPreviewResponse:
    contents = await _read_xlsx(file)
    try:
        return ParentLinkImportPreviewResponse(**build_parent_link_import_preview(db, contents))
    except ImportFileError as exc:
        _raise_file_error(exc)


@router.post("/commit", response_model=ParentLinkImportCommitResponse)
async def commit_parent_link_import_route(
    selected_rows: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ParentLinkImportCommitResponse:
    contents = await _read_xlsx(file)
    try:
        result = commit_parent_link_import(db, contents, _selected_rows(selected_rows), current_user)
        return ParentLinkImportCommitResponse(**result)
    except ImportFileError as exc:
        _raise_file_error(exc)
