import os
import smtplib
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Parent, ReportCard, StudentParent


def _get_required_email_config() -> dict:
    config = {
        "smtp_host": os.getenv("SMTP_HOST", "").strip(),
        "smtp_port": os.getenv("SMTP_PORT", "").strip(),
        "smtp_username": os.getenv("SMTP_USERNAME", "").strip(),
        "smtp_password": os.getenv("SMTP_PASSWORD", "").strip(),
        "smtp_from_email": os.getenv("SMTP_FROM_EMAIL", "").strip(),
        "app_base_url": os.getenv("APP_BASE_URL", "").strip(),
    }
    missing = [key.upper() for key, value in config.items() if not value]
    if missing:
        raise ValueError(f"Missing email configuration: {', '.join(missing)}")

    try:
        config["smtp_port"] = int(config["smtp_port"])
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be a number") from exc

    return config


def _build_report_link(app_base_url: str, report_card_id: UUID) -> str:
    return f"{app_base_url.rstrip('/')}/reports/{report_card_id}"


def _build_email_message(config: dict, parent: Parent, report_card: ReportCard) -> EmailMessage:
    student = report_card.student
    student_name = f"{student.first_name} {student.last_name}"
    report_link = _build_report_link(config["app_base_url"], report_card.id)
    parent_name = parent.user.name if parent.user and parent.user.name else "Parent/Guardian"

    message = EmailMessage()
    message["Subject"] = f"Report card available for {student_name}"
    message["From"] = config["smtp_from_email"]
    message["To"] = parent.user.email
    message.set_content(
        "\n".join(
            [
                f"Dear {parent_name},",
                "",
                f"{student_name}'s report card for {report_card.term} {report_card.school_year} is now available.",
                "",
                f"You can view it securely here: {report_link}",
                "",
                "Best regards,",
                "School Administration",
            ]
        )
    )
    return message


def _send_email(config: dict, message: EmailMessage) -> None:
    if config["smtp_port"] == 465:
        with smtplib.SMTP_SSL(config["smtp_host"], config["smtp_port"]) as smtp:
            smtp.login(config["smtp_username"], config["smtp_password"])
            smtp.send_message(message)
        return

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as smtp:
        smtp.starttls()
        smtp.login(config["smtp_username"], config["smtp_password"])
        smtp.send_message(message)


def send_report_notification_to_parents(db: Session, report_card_id: UUID) -> list[dict]:
    config = _get_required_email_config()
    report_card = db.get(ReportCard, report_card_id)
    if report_card is None:
        raise ValueError("Report card not found")

    parents = db.scalars(
        select(Parent)
        .join(StudentParent, StudentParent.parent_id == Parent.id)
        .where(StudentParent.student_id == report_card.student_id)
    ).all()

    results = []
    for parent in parents:
        email = parent.user.email
        message = _build_email_message(config, parent, report_card)
        try:
            _send_email(config, message)
        except Exception as exc:
            results.append({"email": email, "sent": False, "error": str(exc)})
            continue
        results.append({"email": email, "sent": True, "error": None})

    return results
