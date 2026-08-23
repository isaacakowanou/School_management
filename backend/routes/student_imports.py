"""Admin-only XLSX preview and synchronous student import endpoints."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import User
from schemas import StudentImportCommitResponse, StudentImportPreviewResponse
from services.student_import import (
    StudentImportFileError,
    build_student_import_preview,
    commit_student_import,
)


router = APIRouter(tags=["students"])
MAX_FILE_BYTES = 5 * 1024 * 1024


def _raise_file_error(exc: StudentImportFileError) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


async def _read_xlsx(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "student_import_invalid_file_type",
                "message": "Upload an .xlsx workbook.",
            },
        )
    contents = await file.read(MAX_FILE_BYTES + 1)
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "student_import_file_too_large",
                "message": "The workbook must be 5 MB or smaller.",
            },
        )
    return contents


@router.post("/preview", response_model=StudentImportPreviewResponse)
async def preview_student_import(
    school_year: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StudentImportPreviewResponse:
    contents = await _read_xlsx(file)
    try:
        result = build_student_import_preview(db, contents, school_year)
    except StudentImportFileError as exc:
        _raise_file_error(exc)
    return StudentImportPreviewResponse(**result)


@router.post("/commit", response_model=StudentImportCommitResponse)
async def commit_student_import_route(
    school_year: str = Form(...),
    selected_rows: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StudentImportCommitResponse:
    try:
        parsed_selection = json.loads(selected_rows)
        if not isinstance(parsed_selection, list) or any(
            isinstance(value, bool) or not isinstance(value, int) for value in parsed_selection
        ):
            raise ValueError
        selected = set(parsed_selection)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "student_import_invalid_selection",
                "message": "selected_rows must be a JSON array of spreadsheet row numbers.",
            },
        ) from exc

    contents = await _read_xlsx(file)
    try:
        result = commit_student_import(db, contents, school_year, selected, current_user)
    except StudentImportFileError as exc:
        _raise_file_error(exc)
    return StudentImportCommitResponse(**result)
