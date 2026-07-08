import os
import smtplib
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, Grade, GradeItem, Parent, ReportCard, Student, StudentParent


SUPPORTED_EMAIL_PROVIDERS = {"resend", "smtp"}


def _clean_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _redact(value: str, secrets: list[str]) -> str:
    cleaned = value
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    if len(cleaned) > 300:
        return f"{cleaned[:297]}..."
    return cleaned


def _sanitize_error(exc: Exception, secrets: list[str]) -> str:
    return _redact(str(exc) or exc.__class__.__name__, secrets)


def _missing_config_error(names: list[str]) -> ValueError:
    return ValueError(f"Missing email configuration: {', '.join(names)}")


def _select_email_provider() -> str:
    configured_provider = _clean_env("EMAIL_PROVIDER").lower()
    if configured_provider:
        if configured_provider not in SUPPORTED_EMAIL_PROVIDERS:
            raise ValueError("EMAIL_PROVIDER must be one of: resend, smtp")
        return configured_provider

    if _clean_env("RESEND_API_KEY") or _clean_env("EMAIL_FROM"):
        return "resend"
    if _clean_env("SMTP_HOST") or _clean_env("SMTP_FROM_EMAIL"):
        return "smtp"
    return "resend"


def _get_email_config() -> dict:
    provider = _select_email_provider()
    app_base_url = _clean_env("APP_BASE_URL")
    if not app_base_url:
        raise _missing_config_error(["APP_BASE_URL"])

    if provider == "resend":
        config = {
            "provider": "resend",
            "resend_api_key": _clean_env("RESEND_API_KEY"),
            "email_from": _clean_env("EMAIL_FROM"),
            "app_base_url": app_base_url,
        }
        missing = [
            name
            for name, value in {
                "RESEND_API_KEY": config["resend_api_key"],
                "EMAIL_FROM": config["email_from"],
            }.items()
            if not value
        ]
        if missing:
            raise _missing_config_error(missing)
        return config

    config = {
        "provider": "smtp",
        "smtp_host": _clean_env("SMTP_HOST"),
        "smtp_port": _clean_env("SMTP_PORT"),
        "smtp_username": _clean_env("SMTP_USERNAME"),
        "smtp_password": _clean_env("SMTP_PASSWORD"),
        "smtp_from_email": _clean_env("SMTP_FROM_EMAIL"),
        "app_base_url": app_base_url,
    }
    missing = [
        name
        for name, value in {
            "SMTP_HOST": config["smtp_host"],
            "SMTP_PORT": config["smtp_port"],
            "SMTP_USERNAME": config["smtp_username"],
            "SMTP_PASSWORD": config["smtp_password"],
            "SMTP_FROM_EMAIL": config["smtp_from_email"],
        }.items()
        if not value
    ]
    if missing:
        raise _missing_config_error(missing)

    try:
        config["smtp_port"] = int(config["smtp_port"])
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be a number") from exc

    return config


def _config_secrets(config: dict) -> list[str]:
    return [
        config.get("resend_api_key", ""),
        config.get("smtp_username", ""),
        config.get("smtp_password", ""),
    ]


def _build_report_link(app_base_url: str, report_card_id: UUID) -> str:
    return f"{app_base_url.rstrip('/')}/reports/{report_card_id}"


def _build_email_body(parent_name: str, report_link: str) -> str:
    return "\n".join(
        [
            f"Dear {parent_name},",
            "",
            "A report card is available. Please log in to view it.",
            "",
            report_link,
            "",
            "Best regards,",
            "School Administration",
        ]
    )


def _send_resend_email(config: dict, *, to_email: str, subject: str, body: str) -> str | None:
    import resend

    resend.api_key = config["resend_api_key"]
    response = resend.Emails.send(
        {
            "from": config["email_from"],
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
    )
    if isinstance(response, dict):
        return response.get("id")
    return getattr(response, "id", None)


def _build_smtp_message(config: dict, *, to_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["smtp_from_email"]
    message["To"] = to_email
    message.set_content(body)
    return message


def _send_smtp_email(config: dict, *, to_email: str, subject: str, body: str) -> None:
    message = _build_smtp_message(config, to_email=to_email, subject=subject, body=body)
    if config["smtp_port"] == 465:
        with smtplib.SMTP_SSL(config["smtp_host"], config["smtp_port"]) as smtp:
            smtp.login(config["smtp_username"], config["smtp_password"])
            smtp.send_message(message)
        return

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as smtp:
        smtp.starttls()
        smtp.login(config["smtp_username"], config["smtp_password"])
        smtp.send_message(message)


def send_report_available_email(
    to_email: str,
    parent_name: str,
    report_link: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    provider = config["provider"]
    subject = "Report card available"
    body = _build_email_body(parent_name, report_link)
    secrets = _config_secrets(config)
    clean_to_email = (to_email or "").strip()

    if not clean_to_email:
        return {
            "email": clean_to_email or None,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": "Parent email is missing",
        }

    try:
        if provider == "resend":
            provider_message_id = _send_resend_email(
                config,
                to_email=clean_to_email,
                subject=subject,
                body=body,
            )
        else:
            _send_smtp_email(config, to_email=clean_to_email, subject=subject, body=body)
            provider_message_id = None
    except Exception as exc:
        return {
            "email": clean_to_email,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": _sanitize_error(exc, secrets),
        }

    return {
        "email": clean_to_email,
        "sent": True,
        "success": True,
        "provider": provider,
        "provider_message_id": provider_message_id,
        "error": None,
    }


def _build_account_created_body(name: str, email: str, temp_password: str, app_base_url: str) -> str:
    return "\n".join(
        [
            f"Dear {name},",
            "",
            "Your account has been created for GGFK School Management.",
            "",
            f"Email:    {email}",
            f"Password: {temp_password}",
            "",
            f"Please log in at {app_base_url.rstrip('/')} and change your password immediately.",
            "",
            "Best regards,",
            "School Administration",
        ]
    )


def send_account_created_email(
    name: str,
    to_email: str,
    temp_password: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    provider = config["provider"]
    subject = "Your GGFK account has been created"
    body = _build_account_created_body(name, to_email, temp_password, config["app_base_url"])
    secrets = _config_secrets(config)
    clean_to_email = (to_email or "").strip()

    if not clean_to_email:
        return {
            "email": None,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": "Email address is missing",
        }

    try:
        if provider == "resend":
            provider_message_id = _send_resend_email(
                config,
                to_email=clean_to_email,
                subject=subject,
                body=body,
            )
        else:
            _send_smtp_email(config, to_email=clean_to_email, subject=subject, body=body)
            provider_message_id = None
    except Exception as exc:
        return {
            "email": clean_to_email,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": _sanitize_error(exc, secrets),
        }

    return {
        "email": clean_to_email,
        "sent": True,
        "success": True,
        "provider": provider,
        "provider_message_id": provider_message_id,
        "error": None,
    }


def _build_grades_email_body(
    parent_name: str,
    student_name: str,
    course_name: str,
    term: str,
    grade_lines: list[str],
    app_base_url: str,
) -> str:
    lines_block = "\n".join(f"  {line}" for line in grade_lines) if grade_lines else "  —"
    portal = app_base_url.rstrip("/")
    return "\n".join(
        [
            f"Cher(e) {parent_name},",
            "",
            f"Les notes de {student_name} ont été mises à jour pour le cours {course_name} ({term}).",
            "",
            lines_block,
            "",
            "Connectez-vous pour voir le bulletin complet :",
            portal,
            "",
            "---",
            "",
            f"Dear {parent_name},",
            "",
            f"Grades for {student_name} have been updated for the course {course_name} ({term}).",
            "",
            lines_block,
            "",
            "Log in to view the full report:",
            portal,
            "",
            "Best regards,",
            "School Administration / Administration scolaire",
        ]
    )


def send_grade_notification_email(
    to_email: str,
    parent_name: str,
    student_name: str,
    course_name: str,
    term: str,
    grade_lines: list[str],
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    provider = config["provider"]
    subject = f"Nouvelles notes de {student_name} — {course_name}"
    body = _build_grades_email_body(
        parent_name, student_name, course_name, term, grade_lines, config["app_base_url"]
    )
    secrets = _config_secrets(config)
    clean_to_email = (to_email or "").strip()

    if not clean_to_email:
        return {
            "email": None,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": "Parent email is missing",
        }

    try:
        if provider == "resend":
            provider_message_id = _send_resend_email(
                config, to_email=clean_to_email, subject=subject, body=body
            )
        else:
            _send_smtp_email(config, to_email=clean_to_email, subject=subject, body=body)
            provider_message_id = None
    except Exception as exc:
        return {
            "email": clean_to_email,
            "sent": False,
            "success": False,
            "provider": provider,
            "provider_message_id": None,
            "error": _sanitize_error(exc, secrets),
        }

    return {
        "email": clean_to_email,
        "sent": True,
        "success": True,
        "provider": provider,
        "provider_message_id": provider_message_id,
        "error": None,
    }


def send_grades_notification(db: Session, course: Course, student: Student) -> list[dict]:
    from services.sms_service import send_grades_available_sms

    try:
        email_config = _get_email_config()
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).warning("Email config missing, skipping grade notification: %s", exc)
        return []

    grades = db.scalars(
        select(Grade)
        .join(Grade.grade_item)
        .where(
            GradeItem.course_id == course.id,
            GradeItem.deleted_at.is_(None),
            Grade.student_id == student.id,
            Grade.deleted_at.is_(None),
        )
        .order_by(GradeItem.title)
    ).all()

    grade_lines = [
        f"{g.grade_item.title} : {g.score}/{g.grade_item.max_score}"
        for g in grades
    ]
    student_name = f"{student.first_name} {student.last_name}"

    parents = db.scalars(
        select(Parent)
        .join(StudentParent, StudentParent.parent_id == Parent.id)
        .where(
            StudentParent.student_id == student.id,
            StudentParent.deleted_at.is_(None),
            Parent.deleted_at.is_(None),
        )
    ).all()

    results = []
    for parent in parents:
        parent_name = parent.user.name if parent.user and parent.user.name else "Parent/Guardian"

        if parent.user.email:
            results.append(
                send_grade_notification_email(
                    parent.user.email,
                    parent_name,
                    student_name,
                    course.name,
                    course.term,
                    grade_lines,
                    config=email_config,
                )
            )

        if parent.phone:
            results.extend(
                send_grades_available_sms(
                    phone=parent.phone,
                    student_name=student_name,
                    course_name=course.name,
                    term=course.term,
                )
            )

    return results


def send_report_notification_to_parents(db: Session, report_card_id: UUID) -> list[dict]:
    from services.sms_service import send_report_available_sms

    email_config = _get_email_config()
    report_card = db.get(ReportCard, report_card_id)
    if report_card is None or report_card.deleted_at is not None or report_card.student.deleted_at is not None:
        raise ValueError("Report card not found")

    report_link = _build_report_link(email_config["app_base_url"], report_card.id)
    student = report_card.student
    student_name = f"{student.first_name} {student.last_name}"
    term = report_card.term

    parents = db.scalars(
        select(Parent)
        .join(StudentParent, StudentParent.parent_id == Parent.id)
        .where(
            StudentParent.student_id == report_card.student_id,
            StudentParent.deleted_at.is_(None),
            Parent.deleted_at.is_(None),
        )
    ).all()

    results = []
    for parent in parents:
        parent_name = parent.user.name if parent.user and parent.user.name else "Parent/Guardian"

        if parent.user.email:
            results.append(
                send_report_available_email(
                    parent.user.email,
                    parent_name,
                    report_link,
                    config=email_config,
                )
            )

        if parent.phone:
            sms_results = send_report_available_sms(
                phone=parent.phone,
                student_name=student_name,
                term=term,
                report_card_id=report_card.id,
            )
            results.extend(sms_results)

    return results
