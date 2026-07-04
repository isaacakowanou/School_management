import logging
import os
from uuid import UUID

logger = logging.getLogger(__name__)


def _clean_env(name: str) -> str:
    return os.getenv(name, "").strip()


def to_e164(phone: str) -> str:
    """Normalise a phone number to E.164.

    Strips whitespace. Prepends +229 (Benin country code) when the number
    doesn't already start with '+'.
    """
    phone = (phone or "").strip()
    if not phone.startswith("+"):
        phone = f"+229{phone}"
    return phone


def _get_twilio_config() -> dict:
    config = {
        "account_sid": _clean_env("TWILIO_ACCOUNT_SID"),
        "auth_token": _clean_env("TWILIO_AUTH_TOKEN"),
        "verify_service_sid": _clean_env("TWILIO_VERIFY_SERVICE_SID"),
        "phone_number": _clean_env("TWILIO_PHONE_NUMBER"),
        "app_base_url": _clean_env("APP_BASE_URL"),
    }
    missing = [k.upper() for k, v in config.items() if not v]
    if missing:
        raise ValueError(f"Missing Twilio configuration: {', '.join(missing)}")
    return config


def _twilio_client(config: dict):
    from twilio.rest import Client  # deferred import — twilio is optional at import time

    return Client(config["account_sid"], config["auth_token"])


# ---------------------------------------------------------------------------
# OTP — Twilio Verify
# ---------------------------------------------------------------------------


def send_otp(phone: str, config: dict | None = None) -> dict:
    """Send an OTP to *phone* via Twilio Verify (SMS channel only).

    Returns a result dict with sent/success/error keys.
    Always catches Twilio exceptions so the caller can silent-fail.
    """
    try:
        cfg = config or _get_twilio_config()
    except ValueError as exc:
        logger.warning("Twilio config missing, skipping OTP send: %s", exc)
        return {"phone": phone, "sent": False, "success": False, "error": str(exc)}

    e164 = to_e164(phone)
    try:
        client = _twilio_client(cfg)
        client.verify.v2.services(cfg["verify_service_sid"]).verifications.create(
            to=e164,
            channel="sms",
        )
        return {"phone": e164, "sent": True, "success": True, "error": None}
    except Exception as exc:
        logger.warning("Twilio Verify send failed for %s: %s", e164, exc)
        return {"phone": e164, "sent": False, "success": False, "error": str(exc)}


def check_otp(phone: str, code: str, config: dict | None = None) -> bool:
    """Check an OTP code via Twilio Verify. Returns True if approved."""
    try:
        cfg = config or _get_twilio_config()
    except ValueError as exc:
        logger.warning("Twilio config missing, OTP check will fail: %s", exc)
        return False

    e164 = to_e164(phone)
    try:
        client = _twilio_client(cfg)
        result = client.verify.v2.services(cfg["verify_service_sid"]).verification_checks.create(
            to=e164,
            code=code,
        )
        return result.status == "approved"
    except Exception as exc:
        logger.warning("Twilio Verify check failed for %s: %s", e164, exc)
        return False


# ---------------------------------------------------------------------------
# Messaging — Twilio Messages API (notifications, not OTP)
# ---------------------------------------------------------------------------


def _send_message(client, *, from_: str, to: str, body: str) -> dict:
    try:
        msg = client.messages.create(from_=from_, to=to, body=body)
        return {"to": to, "sent": True, "success": True, "sid": msg.sid, "error": None}
    except Exception as exc:
        logger.warning("Twilio message failed to %s: %s", to, exc)
        return {"to": to, "sent": False, "success": False, "sid": None, "error": str(exc)}


def _send_sms_and_whatsapp(phone: str, body: str, config: dict) -> list[dict]:
    """Send *body* to *phone* via both SMS and WhatsApp. Returns two result dicts."""
    e164 = to_e164(phone)
    client = _twilio_client(config)
    sms_from = config["phone_number"]
    wa_from = f"whatsapp:{sms_from}" if not sms_from.startswith("whatsapp:") else sms_from

    sms_result = _send_message(client, from_=sms_from, to=e164, body=body)
    sms_result["channel"] = "sms"
    wa_result = _send_message(client, from_=wa_from, to=f"whatsapp:{e164}", body=body)
    wa_result["channel"] = "whatsapp"
    return [sms_result, wa_result]


def send_account_created_sms(
    name: str,
    phone: str,
    temp_password: str,
    config: dict | None = None,
) -> list[dict]:
    """Notify a newly-created user of their temporary password via SMS + WhatsApp."""
    try:
        cfg = config or _get_twilio_config()
    except ValueError as exc:
        logger.warning("Twilio config missing, skipping account-created SMS: %s", exc)
        return [{"phone": phone, "sent": False, "success": False, "error": str(exc)}]

    app_url = cfg["app_base_url"].rstrip("/")
    body = (
        f"Your GGFK School account has been created.\n"
        f"Temporary password: {temp_password}\n"
        f"Log in at {app_url} and change it immediately."
    )

    try:
        return _send_sms_and_whatsapp(phone, body, cfg)
    except Exception as exc:
        logger.warning("Twilio account-created SMS failed for %s: %s", phone, exc)
        return [{"phone": phone, "sent": False, "success": False, "error": str(exc)}]


def send_report_available_sms(
    phone: str,
    student_name: str,
    term: str,
    report_card_id: UUID,
    config: dict | None = None,
) -> list[dict]:
    """Notify a parent that a report card is ready, via SMS + WhatsApp."""
    try:
        cfg = config or _get_twilio_config()
    except ValueError as exc:
        logger.warning("Twilio config missing, skipping report-available SMS: %s", exc)
        return [{"phone": phone, "sent": False, "success": False, "error": str(exc)}]

    app_url = cfg["app_base_url"].rstrip("/")
    report_link = f"{app_url}/reports/{report_card_id}"
    body = (
        f"{student_name}'s report card for {term} is ready.\n"
        f"Log in to view it: {report_link}"
    )

    try:
        return _send_sms_and_whatsapp(phone, body, cfg)
    except Exception as exc:
        logger.warning("Twilio report-available SMS failed for %s: %s", phone, exc)
        return [{"phone": phone, "sent": False, "success": False, "error": str(exc)}]
