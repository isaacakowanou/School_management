import os
import smtplib
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Parent, ReportCard, StudentParent


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


def send_report_notification_to_parents(db: Session, report_card_id: UUID) -> list[dict]:
    config = _get_email_config()
    report_card = db.get(ReportCard, report_card_id)
    if report_card is None or report_card.deleted_at is not None or report_card.student.deleted_at is not None:
        raise ValueError("Report card not found")

    report_link = _build_report_link(config["app_base_url"], report_card.id)
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
        results.append(
            send_report_available_email(
                parent.user.email,
                parent_name,
                report_link,
                config=config,
            )
        )

    return results
