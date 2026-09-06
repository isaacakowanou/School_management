"""Preview and commit parent links for existing active students.

The importer never creates students. It reuses active parent accounts by
canonical email, creates one account per new email, and reactivates a prior
soft-deleted StudentParent link rather than duplicating it. Existing parent
identity is authoritative: differing workbook name/phone values are warnings
and are never written over the stored profile.
"""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import hash_password
from models import Parent, Student, StudentParent, User
from services.email_service import send_account_created_email
from services.import_common import EMAIL_PATTERN, ImportFileError, canonical_email, issue, parse_workbook


REQUIRED_COLUMNS = ("student_number", "parent_name", "parent_email")
OPTIONAL_COLUMNS = ("parent_phone", "relationship")


def parse_parent_link_workbook(file_bytes: bytes) -> list[dict]:
    return parse_workbook(
        file_bytes,
        required_columns=REQUIRED_COLUMNS,
        optional_columns=OPTIONAL_COLUMNS,
        code_prefix="parent_link_import",
        row_label="parent-link",
    )


def _active_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User)
        .options(joinedload(User.parent_profile))
        .where(func.lower(User.email) == email, User.deleted_at.is_(None))
    )


def _active_student_by_number(db: Session, student_number: str) -> Student | None:
    return db.scalar(
        select(Student).where(
            Student.student_number == student_number,
            Student.deleted_at.is_(None),
            Student.academic_status == "active",
        )
    )


def _link_state(db: Session, student_id, parent_id) -> tuple[str, StudentParent | None]:
    active_link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student_id,
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
        )
    )
    if active_link is not None:
        return "skip_existing", active_link
    deleted_link = db.scalar(
        select(StudentParent)
        .where(
            StudentParent.student_id == student_id,
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_not(None),
        )
        .order_by(StudentParent.deleted_at.desc())
    )
    return ("reactivate", deleted_link) if deleted_link is not None else ("link", None)


def build_parent_link_import_preview(
    db: Session,
    file_bytes: bytes,
    selected_rows: set[int] | None = None,
) -> dict:
    parsed_rows = parse_parent_link_workbook(file_bytes)
    if selected_rows is not None:
        parsed_rows = [row for row in parsed_rows if row["row_number"] in selected_rows]

    names_by_email: dict[str, set[str]] = defaultdict(set)
    phones_by_email: dict[str, set[str]] = defaultdict(set)
    pairs: list[tuple[str, str]] = []
    for row in parsed_rows:
        email = canonical_email(row["parent_email"])
        if email:
            names_by_email[email].add(row["parent_name"].strip().casefold())
            if row["parent_phone"].strip():
                phones_by_email[email].add(row["parent_phone"].strip())
        pairs.append((row["student_number"].strip(), email))
    duplicate_pairs = {pair for pair, count in Counter(pairs).items() if count > 1}

    active_users: dict[str, User | None] = {}
    first_valid_email: set[str] = set()
    preview_rows: list[dict] = []
    for row in parsed_rows:
        errors: list[dict] = []
        warnings: list[dict] = []
        student_number = row["student_number"].strip()
        parent_name = row["parent_name"].strip()
        parent_email = canonical_email(row["parent_email"])
        parent_phone = row["parent_phone"].strip()
        relationship = row["relationship"].strip()

        for field, value in (
            ("student_number", student_number),
            ("parent_name", parent_name),
            ("parent_email", parent_email),
        ):
            if not value:
                errors.append(issue("parent_link_import_required", field, f"{field} is required."))

        if parent_email and not EMAIL_PATTERN.fullmatch(parent_email):
            errors.append(
                issue("parent_link_import_invalid_email", "parent_email", "Parent email is invalid.")
            )
        if (student_number, parent_email) in duplicate_pairs:
            errors.append(
                issue(
                    "parent_link_import_duplicate_row",
                    None,
                    "This student and parent email appear more than once in the workbook.",
                )
            )
        if parent_email and len(names_by_email[parent_email]) > 1:
            errors.append(
                issue(
                    "parent_link_import_parent_name_conflict",
                    "parent_name",
                    "The same parent email has conflicting names in this workbook.",
                )
            )
        if parent_email and len(phones_by_email[parent_email]) > 1:
            warnings.append(
                issue(
                    "parent_link_import_parent_details_differ",
                    "parent_phone",
                    "The same parent email has different phone values; only the first new value is kept.",
                )
            )

        student = _active_student_by_number(db, student_number) if student_number else None
        if student_number and student is None:
            errors.append(
                issue(
                    "parent_link_import_student_not_found",
                    "student_number",
                    "No active student has this student number.",
                )
            )

        parent_action = "create"
        link_action = "link"
        active_user = None
        if parent_email:
            if parent_email not in active_users:
                active_users[parent_email] = _active_user_by_email(db, parent_email)
            active_user = active_users[parent_email]
            if active_user is not None:
                parent = active_user.parent_profile
                if active_user.role != "parent" or parent is None or parent.deleted_at is not None:
                    errors.append(
                        issue(
                            "parent_link_import_email_role_conflict",
                            "parent_email",
                            "This email belongs to an active non-parent account.",
                        )
                    )
                else:
                    parent_action = "reuse"
                    differences: list[str] = []
                    if active_user.name.strip().casefold() != parent_name.casefold():
                        differences.append("name")
                    if parent_phone and (parent.phone or "").strip() != parent_phone:
                        differences.append("phone")
                    if differences:
                        warnings.append(
                            issue(
                                "parent_link_import_parent_details_differ",
                                None,
                                "Existing parent reused; workbook name/phone values are ignored.",
                            )
                        )
                    if student is not None:
                        link_action, _ = _link_state(db, student.id, parent.id)
                        if link_action == "skip_existing":
                            warnings.append(
                                issue(
                                    "parent_link_import_link_exists",
                                    None,
                                    "This parent is already linked to the student.",
                                )
                            )
            elif parent_email in first_valid_email:
                parent_action = "reuse"

        is_valid = not errors
        if is_valid and active_user is None:
            first_valid_email.add(parent_email)
        preview_rows.append(
            {
                "row_number": row["row_number"],
                "student_number": student_number,
                "student_id": student.id if student else None,
                "student_name": f"{student.first_name} {student.last_name}" if student else None,
                "parent_name": parent_name,
                "parent_email": parent_email,
                "parent_phone": parent_phone,
                "relationship": relationship,
                "parent_action": parent_action,
                "link_action": link_action,
                "is_valid": is_valid,
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


def _link_parent_row(
    db: Session,
    row: dict,
    current_user: User,
    parent_cache: dict[str, Parent],
) -> tuple[dict, tuple[Parent, str] | None, bool, bool]:
    student = _active_student_by_number(db, row["student_number"])
    if student is None:
        raise ValueError("Student is no longer available")

    email = row["parent_email"]
    active_user = _active_user_by_email(db, email)
    parent = active_user.parent_profile if active_user and active_user.role == "parent" else None
    if active_user is not None and (parent is None or parent.deleted_at is not None):
        raise ValueError("Email belongs to another active role")

    parent_created = False
    notification: tuple[Parent, str] | None = None
    if email in parent_cache:
        parent = parent_cache[email]
    elif parent is None:
        temp_password = secrets.token_urlsafe(9)
        user = User(
            name=row["parent_name"],
            email=email,
            password_hash=hash_password(temp_password),
            role="parent",
            must_change_password=True,
        )
        parent = Parent(user=user, phone=row["parent_phone"] or None)
        db.add_all([user, parent])
        db.flush()
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="parent_created",
            entity_type="parent",
            entity_id=parent.id,
            old_value=None,
            new_value={
                "user_id": parent.user_id,
                "name": user.name,
                "email": user.email,
                "phone": parent.phone,
                "source": "parent_link_import",
            },
        )
        parent_created = True
        notification = (parent, temp_password)
    parent_cache[email] = parent

    action, prior_link = _link_state(db, student.id, parent.id)
    if action == "skip_existing":
        return (
            {
                "row_number": row["row_number"],
                "status": "skipped_existing",
                "student_id": student.id,
                "parent_id": parent.id,
                "link_id": prior_link.id,
                "parent_action": "create" if parent_created else "reuse",
            },
            notification,
            parent_created,
            not parent_created,
        )

    if action == "reactivate":
        link = prior_link
        link.deleted_at = None
        link.deleted_batch_id = None
        link.relationship = row["relationship"] or None
    else:
        link = StudentParent(
            student_id=student.id,
            parent_id=parent.id,
            relationship=row["relationship"] or None,
        )
        db.add(link)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="parent_linked_to_student",
        entity_type="student_parent",
        entity_id=link.id,
        old_value=None,
        new_value={
            "student_id": student.id,
            "parent_id": parent.id,
            "relationship": link.relationship,
            "link_action": action,
            "source": "parent_link_import",
        },
    )
    return (
        {
            "row_number": row["row_number"],
            "status": "reactivated" if action == "reactivate" else "linked",
            "student_id": student.id,
            "parent_id": parent.id,
            "link_id": link.id,
            "parent_action": "create" if parent_created else "reuse",
        },
        notification,
        parent_created,
        not parent_created,
    )


def commit_parent_link_import(
    db: Session,
    file_bytes: bytes,
    selected_rows: set[int],
    current_user: User,
) -> dict:
    parsed_rows = parse_parent_link_workbook(file_bytes)
    available_rows = {row["row_number"] for row in parsed_rows}
    if not selected_rows:
        raise ImportFileError("parent_link_import_no_rows_selected", "Select at least one row.")
    if not selected_rows.issubset(available_rows):
        raise ImportFileError(
            "parent_link_import_invalid_selection",
            "Selected rows do not match the uploaded workbook.",
        )

    preview = build_parent_link_import_preview(db, file_bytes, selected_rows=selected_rows)
    parent_cache: dict[str, Parent] = {}
    created_emails: set[str] = set()
    reused_emails: set[str] = set()
    notifications: dict[str, tuple[Parent, str]] = {}
    rows: list[dict] = []
    failures: list[dict] = []

    for preview_row in preview["rows"]:
        if not preview_row["is_valid"]:
            failures.append({"row_number": preview_row["row_number"], "errors": preview_row["errors"]})
            rows.append({"row_number": preview_row["row_number"], "status": "failed"})
            continue
        cached_before = set(parent_cache)
        try:
            with db.begin_nested():
                result, notification, parent_created, parent_reused = _link_parent_row(
                    db,
                    preview_row,
                    current_user,
                    parent_cache,
                )
            rows.append(result)
            email = preview_row["parent_email"]
            if parent_created:
                created_emails.add(email)
                reused_emails.discard(email)
                if notification is not None:
                    notifications[email] = notification
            elif parent_reused and email not in created_emails:
                reused_emails.add(email)
        except (IntegrityError, ValueError):
            for email in set(parent_cache) - cached_before:
                parent_cache.pop(email, None)
            errors = [
                issue(
                    "parent_link_import_commit_conflict",
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
    for email, (parent, temp_password) in notifications.items():
        try:
            result = send_account_created_email(
                name=parent.user.name,
                to_email=email,
                temp_password=temp_password,
            )
        except Exception as exc:
            result = {"success": False, "error": str(exc)[:300] or exc.__class__.__name__}
        success = bool(result.get("success"))
        emails_sent += int(success)
        emails_failed += int(not success)
        email_results.append(
            {
                "parent_id": parent.id,
                "email": email,
                "success": success,
                "error": result.get("error"),
                "temp_password": None if success else temp_password,
            }
        )

    return {
        "status": "ok",
        "linked": sum(1 for row in rows if row["status"] == "linked"),
        "reactivated": sum(1 for row in rows if row["status"] == "reactivated"),
        "skipped_existing": sum(1 for row in rows if row["status"] == "skipped_existing"),
        "failed": len(failures),
        "parents_reused": len(reused_emails),
        "parents_created": len(created_emails),
        "emails_sent": emails_sent,
        "emails_failed": emails_failed,
        "rows": rows,
        "failures": failures,
        "email_results": email_results,
    }
