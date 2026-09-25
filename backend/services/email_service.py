"""Transactional email delivery and parent notification dispatch.

Resend is the launch email path, with SMTP retained as an environment-selected
fallback. A ``resend.dev`` sender is test mode and can reach only the Resend
account-owner inbox; production delivery needs DNS verification and a school
``EMAIL_FROM`` value, not code changes. Credential emails intentionally contain
plaintext temporary passwords because those credentials are short-lived,
force a first-login change, and invalidate prior sessions. Welcome and
administrator-reset notices are bilingual (French first) and use distinct
wording so a reset is never described as account creation.

Grade-entry and correction notifications name the student/course but expose no
score or average; bulletin-send notifications link to the approved/sent snapshot.
Averages remain inside authenticated bulletins, never notification bodies.
Dispatch targets only active parent links and profiles and returns structured
per-channel outcomes so callers can distinguish delivery from state changes.
"""

import os
import smtplib
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, Parent, ReportCard, Student, StudentParent


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


def _warn_if_sandbox_sender(email_from: str) -> None:
    # Resend's onboarding sender only delivers to the account owner's own
    # inbox — parents receive nothing. A verified school-domain sender
    # (EMAIL_FROM=notifications@<school-domain>) is required in production.
    if email_from.lower().endswith("@resend.dev"):
        import logging

        logging.getLogger(__name__).warning(
            "EMAIL_FROM is a resend.dev sandbox address (%s): emails will only "
            "reach the Resend account owner. Configure a verified school domain.",
            email_from,
        )


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
        _warn_if_sandbox_sender(config["email_from"])
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
            f"Bonjour {parent_name},",
            "",
            "Un bulletin est disponible. Connectez-vous pour le consulter.",
            "",
            report_link,
            "",
            "---",
            "",
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
    subject = "Bulletin disponible / Report card available"
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
    # Plaintext is limited to the generated forced-change credential. Do not
    # reuse this channel for permanent passwords or write the value to logs.
    return "\n".join(
        [
            f"Bonjour {name},",
            "",
            "Votre compte GGFK a été créé.",
            "",
            f"Adresse e-mail : {email}",
            f"Mot de passe temporaire : {temp_password}",
            "",
            f"Veuillez vous connecter à {app_base_url.rstrip('/')} et créer votre propre mot de passe lors de votre première connexion.",
            "",
            "Cordialement,",
            "L'administration scolaire",
            "",
            "---",
            "",
            f"Hello {name},",
            "",
            "Your GGFK account has been created.",
            "",
            f"Email: {email}",
            f"Temporary password: {temp_password}",
            "",
            f"Please log in at {app_base_url.rstrip('/')} and set your own password the first time you sign in.",
            "",
            "Best regards,",
            "School Administration",
        ]
    )


def _send_temporary_credential_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    config: dict,
) -> dict:
    provider = config["provider"]
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


def send_account_created_email(
    name: str,
    to_email: str,
    temp_password: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    return _send_temporary_credential_email(
        to_email=to_email,
        subject="Bienvenue sur GGFK / Welcome to GGFK",
        body=_build_account_created_body(name, to_email, temp_password, config["app_base_url"]),
        config=config,
    )


def _build_temporary_password_reset_body(
    name: str,
    email: str,
    temp_password: str,
    app_base_url: str,
) -> str:
    return "\n".join(
        [
            f"Bonjour {name},",
            "",
            "Votre mot de passe temporaire GGFK a été réinitialisé par l'administration.",
            "",
            f"Adresse e-mail : {email}",
            f"Mot de passe temporaire : {temp_password}",
            "",
            f"Veuillez vous connecter à {app_base_url.rstrip('/')} et créer votre propre mot de passe lors de votre prochaine connexion.",
            "",
            "Cordialement,",
            "L'administration scolaire",
            "",
            "---",
            "",
            f"Hello {name},",
            "",
            "Your temporary GGFK password has been reset by the school administration.",
            "",
            f"Email: {email}",
            f"Temporary password: {temp_password}",
            "",
            f"Please log in at {app_base_url.rstrip('/')} and set your own password the next time you sign in.",
            "",
            "Best regards,",
            "School Administration",
        ]
    )


def send_temporary_password_reset_email(
    name: str,
    to_email: str,
    temp_password: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    return _send_temporary_credential_email(
        to_email=to_email,
        subject="Nouveau mot de passe temporaire GGFK / New temporary GGFK password",
        body=_build_temporary_password_reset_body(
            name,
            to_email,
            temp_password,
            config["app_base_url"],
        ),
        config=config,
    )


def send_password_reset_email(
    name: str,
    to_email: str,
    reset_token: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    reset_link = f"{config['app_base_url'].rstrip('/')}/reset-password?token={reset_token}"
    subject = "Réinitialisation de votre mot de passe GGFK / Reset your GGFK password"
    body = "\n".join(
        [
            f"Bonjour {name},",
            "",
            "Utilisez le lien ci-dessous dans les 45 minutes pour réinitialiser votre mot de passe :",
            reset_link,
            "",
            "Ce lien ne peut être utilisé qu'une seule fois.",
            "",
            f"Hello {name},",
            "",
            "Use the link below within 45 minutes to reset your password:",
            reset_link,
            "",
            "This link can only be used once.",
        ]
    )
    secrets = _config_secrets(config)
    clean_to_email = (to_email or "").strip()
    try:
        if config["provider"] == "resend":
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
            "provider": config["provider"],
            "provider_message_id": None,
            "error": _sanitize_error(exc, secrets),
        }
    return {
        "email": clean_to_email,
        "sent": True,
        "success": True,
        "provider": config["provider"],
        "provider_message_id": provider_message_id,
        "error": None,
    }


def _build_grades_email_body(
    parent_name: str,
    student_name: str,
    course_name: str,
    term: str,
    app_base_url: str,
) -> str:
    # Deliberately contains NO scores: grades are sensitive academic records
    # and email is neither access-controlled nor reliably confidential. The
    # parent logs in to see the actual notes (same pattern as the
    # report-available email).
    portal = app_base_url.rstrip("/")
    return "\n".join(
        [
            f"Cher(e) {parent_name},",
            "",
            f"De nouvelles notes ont été enregistrées pour {student_name} en {course_name} ({term}).",
            "",
            "Connectez-vous à votre espace parent pour les consulter :",
            portal,
            "",
            "---",
            "",
            f"Dear {parent_name},",
            "",
            f"New grades have been recorded for {student_name} in {course_name} ({term}).",
            "",
            "Log in to your parent portal to view them:",
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
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    provider = config["provider"]
    subject = f"Nouvelles notes de {student_name} — {course_name}"
    body = _build_grades_email_body(
        parent_name, student_name, course_name, term, config["app_base_url"]
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


def _build_grade_correction_email_body(
    parent_name: str,
    student_name: str,
    course_name: str,
    term: str,
    app_base_url: str,
) -> str:
    portal = app_base_url.rstrip("/")
    return "\n".join(
        [
            f"Cher(e) {parent_name},",
            "",
            f"Une note de {student_name} en {course_name} ({term}) a été corrigée.",
            "Consultez votre espace parent pour voir les informations disponibles :",
            portal,
            "",
            "---",
            "",
            f"Dear {parent_name},",
            "",
            f"A grade for {student_name} in {course_name} ({term}) was corrected.",
            "Check your parent portal for the available information:",
            portal,
            "",
            "Best regards,",
            "School Administration / Administration scolaire",
        ]
    )


def send_grade_correction_email(
    to_email: str,
    parent_name: str,
    student_name: str,
    course_name: str,
    term: str,
    config: dict | None = None,
) -> dict:
    config = config or _get_email_config()
    provider = config["provider"]
    subject = f"Note corrigée pour {student_name} / Grade corrected"
    body = _build_grade_correction_email_body(
        parent_name, student_name, course_name, term, config["app_base_url"]
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


def _empty_grade_notification_summary() -> dict:
    return {
        "recipients": 0,
        "delivered": {"email": 0, "sms": 0},
        "failed": {"email": 0, "sms": 0},
        "skipped": {"email": 0, "sms": 0},
    }


def send_grades_notification(
    db: Session,
    course: Course,
    student: Student,
    *,
    correction: bool = False,
    term: str | None = None,
) -> dict:
    from services.sms_service import (
        _get_messaging_config,
        send_grade_correction_sms,
        send_grades_available_sms,
    )

    try:
        email_config = _get_email_config()
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).warning("Email config missing, skipping grade notification: %s", exc)
        email_config = None

    try:
        sms_config = _get_messaging_config()
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).warning("SMS config missing, skipping grade notification: %s", exc)
        sms_config = None

    student_name = f"{student.first_name} {student.last_name}"
    notification_term = term or course.term

    # Notify once per affected student in the grade-entry workflow. The portal
    # is the disclosure boundary for scores; neither scores nor averages enter
    # email/SMS payloads.
    parents = db.scalars(
        select(Parent)
        .join(StudentParent, StudentParent.parent_id == Parent.id)
        .where(
            StudentParent.student_id == student.id,
            StudentParent.deleted_at.is_(None),
            Parent.deleted_at.is_(None),
        )
        .distinct()
    ).all()

    summary = _empty_grade_notification_summary()
    for parent in parents:
        summary["recipients"] += 1
        parent_name = parent.user.name if parent.user and parent.user.name else "Parent/Guardian"

        if not parent.user.email or email_config is None:
            summary["skipped"]["email"] += 1
        else:
            email_sender = send_grade_correction_email if correction else send_grade_notification_email
            email_result = email_sender(
                parent.user.email,
                parent_name,
                student_name,
                course.name,
                notification_term,
                config=email_config,
            )
            bucket = "delivered" if email_result.get("sent") else "failed"
            summary[bucket]["email"] += 1

        if not parent.phone or sms_config is None:
            summary["skipped"]["sms"] += 1
        else:
            sms_sender = send_grade_correction_sms if correction else send_grades_available_sms
            phone_results = sms_sender(
                phone=parent.phone,
                student_name=student_name,
                course_name=course.name,
                term=notification_term,
                config=sms_config,
            )
            if not phone_results:
                summary["failed"]["sms"] += 1
            for result in phone_results:
                if result.get("skipped"):
                    bucket = "skipped"
                else:
                    bucket = "delivered" if result.get("sent") else "failed"
                summary[bucket]["sms"] += 1

    return summary


def send_report_notification_to_parents(db: Session, report_card_id: UUID) -> list[dict]:
    from services.sms_service import _get_messaging_config, send_report_available_sms

    try:
        email_config = _get_email_config()
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).warning("Email config missing, skipping report email: %s", exc)
        email_config = None
    try:
        sms_config = _get_messaging_config()
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).warning("SMS config missing, skipping report SMS: %s", exc)
        sms_config = None
    report_card = db.get(ReportCard, report_card_id)
    if report_card is None or report_card.deleted_at is not None or report_card.student.deleted_at is not None:
        raise ValueError("Report card not found")

    report_link = (
        _build_report_link(email_config["app_base_url"], report_card.id)
        if email_config is not None
        else None
    )
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
        .distinct()
    ).all()

    results = []
    for parent in parents:
        parent_name = parent.user.name if parent.user and parent.user.name else "Parent/Guardian"

        if parent.user.email and email_config is not None:
            results.append(
                send_report_available_email(
                    parent.user.email,
                    parent_name,
                    report_link,
                    config=email_config,
                )
            )

        if parent.phone and sms_config is not None:
            sms_results = send_report_available_sms(
                phone=parent.phone,
                student_name=student_name,
                term=term,
                report_card_id=report_card.id,
                config=sms_config,
            )
            results.extend(sms_results)

    return results
