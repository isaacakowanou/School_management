"""Preview and commit admin teacher imports without assigning courses.

Teacher identity is permanent. Preview is read-only; commit reparses and
revalidates selected rows, isolates each row with a savepoint, commits database
work before notification, and creates no Course relationships. Active-only
email and employee-number rules are identical to single-teacher creation.
"""

from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import hash_password
from models import Teacher, User
from services.email_service import send_account_created_email
from services.import_common import EMAIL_PATTERN, ImportFileError, canonical_email, issue, parse_workbook


REQUIRED_COLUMNS = ("teacher_name", "teacher_email")
OPTIONAL_COLUMNS = ("teacher_phone", "employee_number")


def parse_teacher_workbook(file_bytes: bytes) -> list[dict]:
    return parse_workbook(
        file_bytes,
        required_columns=REQUIRED_COLUMNS,
        optional_columns=OPTIONAL_COLUMNS,
        code_prefix="teacher_import",
        row_label="teacher",
    )


def _active_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None))
    )


def _active_teacher_by_number(db: Session, employee_number: str) -> Teacher | None:
    return db.scalar(
        select(Teacher).where(
            Teacher.employee_number == employee_number,
            Teacher.deleted_at.is_(None),
        )
    )


def _employee_number_candidates(db: Session, count: int, reserved: set[str]) -> list[str]:
    prefix = f"TCH-{datetime.now(timezone.utc).year}-"
    existing = db.scalars(
        select(Teacher.employee_number).where(
            Teacher.employee_number.like(f"{prefix}%"),
            Teacher.deleted_at.is_(None),
        )
    ).all()
    suffixes: list[int] = []
    for value in existing:
        try:
            suffixes.append(int(value[len(prefix):]))
        except (TypeError, ValueError):
            continue
    number = max(suffixes, default=0) + 1
    candidates: list[str] = []
    while len(candidates) < count:
        candidate = f"{prefix}{number:04d}"
        if candidate not in reserved and _active_teacher_by_number(db, candidate) is None:
            candidates.append(candidate)
            reserved.add(candidate)
        number += 1
    return candidates


def build_teacher_import_preview(
    db: Session,
    file_bytes: bytes,
    selected_rows: set[int] | None = None,
) -> dict:
    parsed_rows = parse_teacher_workbook(file_bytes)
    if selected_rows is not None:
        parsed_rows = [row for row in parsed_rows if row["row_number"] in selected_rows]

    emails = [canonical_email(row["teacher_email"]) for row in parsed_rows if row["teacher_email"]]
    duplicate_emails = {value for value, count in Counter(emails).items() if count > 1}
    supplied_numbers = [row["employee_number"] for row in parsed_rows if row["employee_number"]]
    duplicate_numbers = {value for value, count in Counter(supplied_numbers).items() if count > 1}
    reserved_numbers = set(supplied_numbers)
    generated_numbers = iter(
        _employee_number_candidates(
            db,
            sum(1 for row in parsed_rows if not row["employee_number"]),
            reserved_numbers,
        )
    )

    preview_rows: list[dict] = []
    for row in parsed_rows:
        errors: list[dict] = []
        warnings: list[dict] = []
        name = row["teacher_name"].strip()
        email = canonical_email(row["teacher_email"])
        phone = row["teacher_phone"].strip()
        employee_number = row["employee_number"].strip() or next(generated_numbers)

        if not name:
            errors.append(issue("teacher_import_required", "teacher_name", "teacher_name is required."))
        if not email:
            errors.append(issue("teacher_import_required", "teacher_email", "teacher_email is required."))
        elif not EMAIL_PATTERN.fullmatch(email):
            errors.append(issue("teacher_import_invalid_email", "teacher_email", "Teacher email is invalid."))
        elif email in duplicate_emails:
            errors.append(
                issue(
                    "teacher_import_duplicate_email",
                    "teacher_email",
                    "Teacher email appears more than once in this workbook.",
                )
            )
        elif _active_user_by_email(db, email) is not None:
            errors.append(
                issue(
                    "teacher_import_email_conflict",
                    "teacher_email",
                    "This email belongs to an active account.",
                )
            )

        if row["employee_number"] and employee_number in duplicate_numbers:
            errors.append(
                issue(
                    "teacher_import_duplicate_employee_number",
                    "employee_number",
                    "Employee number appears more than once in this workbook.",
                )
            )
        elif _active_teacher_by_number(db, employee_number) is not None:
            errors.append(
                issue(
                    "teacher_import_employee_number_conflict",
                    "employee_number",
                    "This employee number belongs to an active teacher.",
                )
            )

        preview_rows.append(
            {
                "row_number": row["row_number"],
                "teacher_name": name,
                "teacher_email": email,
                "teacher_phone": phone,
                "employee_number": employee_number,
                "teacher_action": "create",
                "is_valid": not errors,
                "errors": errors,
                "warnings": warnings,
            }
        )

    valid_rows = sum(1 for row in preview_rows if row["is_valid"])
    return {
        "total_rows": len(preview_rows),
        "valid_rows": valid_rows,
        "invalid_rows": len(preview_rows) - valid_rows,
        "rows": preview_rows,
    }


def _create_teacher_row(db: Session, row: dict, current_user: User) -> tuple[dict, tuple[Teacher, str]]:
    if _active_user_by_email(db, row["teacher_email"]) is not None:
        raise ValueError("Email is no longer available")
    if _active_teacher_by_number(db, row["employee_number"]) is not None:
        raise ValueError("Employee number is no longer available")

    temp_password = secrets.token_urlsafe(9)
    user = User(
        name=row["teacher_name"],
        email=row["teacher_email"],
        password_hash=hash_password(temp_password),
        role="teacher",
        must_change_password=True,
    )
    teacher = Teacher(
        user=user,
        phone=row["teacher_phone"] or None,
        employee_number=row["employee_number"],
    )
    db.add_all([user, teacher])
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="teacher_created",
        entity_type="teacher",
        entity_id=teacher.id,
        old_value=None,
        new_value={
            "user_id": teacher.user_id,
            "name": user.name,
            "email": user.email,
            "phone": teacher.phone,
            "employee_number": teacher.employee_number,
            "source": "teacher_import",
        },
    )
    return (
        {
            "row_number": row["row_number"],
            "status": "created",
            "teacher_id": teacher.id,
            "employee_number": teacher.employee_number,
        },
        (teacher, temp_password),
    )


def commit_teacher_import(
    db: Session,
    file_bytes: bytes,
    selected_rows: set[int],
    current_user: User,
) -> dict:
    parsed_rows = parse_teacher_workbook(file_bytes)
    available_rows = {row["row_number"] for row in parsed_rows}
    if not selected_rows:
        raise ImportFileError("teacher_import_no_rows_selected", "Select at least one row.")
    if not selected_rows.issubset(available_rows):
        raise ImportFileError(
            "teacher_import_invalid_selection",
            "Selected rows do not match the uploaded workbook.",
        )

    preview = build_teacher_import_preview(db, file_bytes, selected_rows=selected_rows)
    rows: list[dict] = []
    failures: list[dict] = []
    notifications: list[tuple[Teacher, str]] = []
    for preview_row in preview["rows"]:
        if not preview_row["is_valid"]:
            failures.append({"row_number": preview_row["row_number"], "errors": preview_row["errors"]})
            rows.append({"row_number": preview_row["row_number"], "status": "failed"})
            continue
        try:
            with db.begin_nested():
                result, notification = _create_teacher_row(db, preview_row, current_user)
            rows.append(result)
            notifications.append(notification)
        except (IntegrityError, ValueError):
            errors = [
                issue(
                    "teacher_import_commit_conflict",
                    None,
                    "The row conflicts with current data and could not be imported.",
                )
            ]
            failures.append({"row_number": preview_row["row_number"], "errors": errors})
            rows.append({"row_number": preview_row["row_number"], "status": "failed"})

    db.commit()

    emails_sent = 0
    emails_failed = 0
    email_results: list[dict] = []
    for teacher, temp_password in notifications:
        try:
            result = send_account_created_email(
                name=teacher.user.name,
                to_email=teacher.user.email,
                temp_password=temp_password,
            )
        except Exception as exc:
            result = {"success": False, "error": str(exc)[:300] or exc.__class__.__name__}
        success = bool(result.get("success"))
        emails_sent += int(success)
        emails_failed += int(not success)
        email_results.append(
            {
                "teacher_id": teacher.id,
                "email": teacher.user.email,
                "success": success,
                "error": result.get("error"),
                "temp_password": None if success else temp_password,
            }
        )

    return {
        "status": "ok",
        "created": sum(1 for row in rows if row["status"] == "created"),
        "failed": len(failures),
        "emails_sent": emails_sent,
        "emails_failed": emails_failed,
        "rows": rows,
        "failures": failures,
        "email_results": email_results,
    }
