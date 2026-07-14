"""Optional OTP and provider-switchable messaging for phone delivery.

Twilio Verify remains the OTP mechanism, independently of ``SMS_PROVIDER``.
Ordinary messages use either ``twilio`` or ``africastalking``; an unset or
invalid provider is treated as an unconfigured/skipped channel so delivery can
never block core school records. Africa's Talking uses ``AT_USERNAME``,
``AT_API_KEY``, and optional ``AT_SENDER_ID``. It is SMS-only here: its separate
WhatsApp product is intentionally out of scope and is reported as skipped,
whereas the Twilio provider keeps attempting both SMS and WhatsApp.

Messages announce grades or bulletins without including scores or averages.
Temporary credentials are the sole intentional plaintext secret because first
login forces their replacement.
"""

import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

logger = logging.getLogger(__name__)


def _clean_env(name: str) -> str:
    return os.getenv(name, "").strip()


def to_e164(phone: str) -> str:
    """Normalise current and pre-2024 Benin formats to E.164."""
    raw = (phone or "").strip()
    if not raw:
        raise ValueError("Phone number is required")

    if raw.startswith("00"):
        raw = f"+{raw[2:]}"
    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw[1:])
        if digits.startswith("229"):
            national = digits[3:]
            if len(national) == 8:
                national = f"01{national}"
            if len(national) != 10 or not national.startswith("01"):
                raise ValueError("Invalid Benin phone number")
            return f"+229{national}"
        if not 4 <= len(digits) <= 15:
            raise ValueError("Invalid international phone number")
        return f"+{digits}"

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("229"):
        national = digits[3:]
    else:
        national = digits
    if len(national) == 8:
        national = f"01{national}"
    if len(national) != 10 or not national.startswith("01"):
        raise ValueError("Invalid Benin phone number")
    return f"+229{national}"


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


def _get_messaging_config() -> dict:
    provider = _clean_env("SMS_PROVIDER").lower()
    if provider == "twilio":
        config = {
            "provider": provider,
            "account_sid": _clean_env("TWILIO_ACCOUNT_SID"),
            "auth_token": _clean_env("TWILIO_AUTH_TOKEN"),
            "phone_number": _clean_env("TWILIO_PHONE_NUMBER"),
            "app_base_url": _clean_env("APP_BASE_URL"),
        }
    elif provider == "africastalking":
        config = {
            "provider": provider,
            "username": _clean_env("AT_USERNAME"),
            "api_key": _clean_env("AT_API_KEY"),
            "sender_id": _clean_env("AT_SENDER_ID"),
            "app_base_url": _clean_env("APP_BASE_URL"),
        }
    else:
        raise ValueError("SMS provider is not configured")

    missing = [key.upper() for key, value in config.items() if key != "sender_id" and not value]
    if missing:
        raise ValueError(f"Missing {provider} messaging configuration: {', '.join(missing)}")
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
        return {
            "provider": "twilio",
            "channel": "sms",
            "to": to,
            "sent": True,
            "success": True,
            "skipped": False,
            "provider_message_id": msg.sid,
            "sid": msg.sid,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Twilio message failed to %s: %s", to, exc)
        return {
            "provider": "twilio",
            "channel": "sms",
            "to": to,
            "sent": False,
            "success": False,
            "skipped": False,
            "provider_message_id": None,
            "sid": None,
            "error": str(exc),
        }


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


def _post_africastalking_sms(config: dict, recipients: list[str], body: str) -> dict:
    """Submit one AT request; kept narrow so tests never need network access."""
    sandbox = config["username"].lower() == "sandbox"
    domain = "api.sandbox.africastalking.com" if sandbox else "api.africastalking.com"
    payload = {
        "username": config["username"],
        "to": ",".join(recipients),
        "message": body,
        "bulkSMSMode": 1,
    }
    if config.get("sender_id"):
        payload["from"] = config["sender_id"]
    request = Request(
        f"https://{domain}/version1/messaging",
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "apiKey": config["api_key"],
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GGFK-School-Management/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _skipped_result(*, provider: str | None, channel: str, to: str, reason: str) -> dict:
    return {
        "provider": provider,
        "channel": channel,
        "to": to,
        "sent": False,
        "success": False,
        "skipped": True,
        "provider_message_id": None,
        "sid": None,
        "error": reason,
    }


def _failed_result(*, provider: str, channel: str, to: str, error: str) -> dict:
    return {
        "provider": provider,
        "channel": channel,
        "to": to,
        "sent": False,
        "success": False,
        "skipped": False,
        "provider_message_id": None,
        "sid": None,
        "error": error,
    }


def _send_africastalking_messages(phones: list[str], body: str, config: dict) -> list[dict]:
    recipients = [to_e164(phone) for phone in phones]
    try:
        response = _post_africastalking_sms(config, recipients, body)
    except (HTTPError, URLError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Africa's Talking SMS request failed: %s", exc)
        sms_results = [
            _failed_result(
                provider="africastalking",
                channel="sms",
                to=recipient,
                error=str(exc),
            )
            for recipient in recipients
        ]
    else:
        response_rows = response.get("SMSMessageData", {}).get("Recipients", [])
        rows_by_number = {row.get("number"): row for row in response_rows}
        sms_results = []
        for recipient in recipients:
            row = rows_by_number.get(recipient)
            if row is None:
                sms_results.append(
                    _failed_result(
                        provider="africastalking",
                        channel="sms",
                        to=recipient,
                        error="Recipient missing from Africa's Talking response",
                    )
                )
                continue
            sent = row.get("statusCode") == 101 and str(row.get("status", "")).lower() == "success"
            sms_results.append(
                {
                    "provider": "africastalking",
                    "channel": "sms",
                    "to": recipient,
                    "sent": sent,
                    "success": sent,
                    "skipped": False,
                    "provider_message_id": row.get("messageId"),
                    "sid": row.get("messageId"),
                    "error": None if sent else str(row.get("status") or "SMS submission failed"),
                }
            )

    whatsapp_results = [
        _skipped_result(
            provider="africastalking",
            channel="whatsapp",
            to=recipient,
            reason="WhatsApp is not configured for the Africa's Talking provider",
        )
        for recipient in recipients
    ]
    return sms_results + whatsapp_results


def send_sms_message(
    phone: str,
    body: str,
    config: dict | None = None,
) -> list[dict]:
    """Send one ordinary phone message through the configured provider."""
    try:
        cfg = config or _get_messaging_config()
    except ValueError as exc:
        logger.warning("SMS config missing, skipping message: %s", exc)
        return [
            _skipped_result(
                provider=None,
                channel="sms",
                to=phone,
                reason=str(exc),
            )
        ]

    try:
        if cfg["provider"] == "twilio":
            return _send_sms_and_whatsapp(phone, body, cfg)
        if cfg["provider"] == "africastalking":
            return _send_africastalking_messages([phone], body, cfg)
    except (ValueError, KeyError) as exc:
        logger.warning("SMS message could not be prepared for %s: %s", phone, exc)
        return [
            _failed_result(
                provider=cfg.get("provider", "unknown"),
                channel="sms",
                to=phone,
                error=str(exc),
            )
        ]
    return [
        _skipped_result(
            provider=cfg.get("provider"),
            channel="sms",
            to=phone,
            reason="SMS provider is not supported",
        )
    ]


def send_account_created_sms(
    name: str,
    phone: str,
    temp_password: str,
    config: dict | None = None,
) -> list[dict]:
    """Notify a newly-created user of their forced-change credential."""
    try:
        cfg = config or _get_messaging_config()
    except ValueError as exc:
        logger.warning("SMS config missing, skipping account-created SMS: %s", exc)
        return [_skipped_result(provider=None, channel="sms", to=phone, reason=str(exc))]

    app_url = cfg["app_base_url"].rstrip("/")
    body = (
        f"Your GGFK School account has been created.\n"
        f"Temporary password: {temp_password}\n"
        f"Log in at {app_url} and change it immediately."
    )

    try:
        return send_sms_message(phone, body, cfg)
    except Exception as exc:
        logger.warning("Twilio account-created SMS failed for %s: %s", phone, exc)
        return [_failed_result(provider=cfg["provider"], channel="sms", to=phone, error=str(exc))]


def send_report_available_sms(
    phone: str,
    student_name: str,
    term: str,
    report_card_id: UUID,
    config: dict | None = None,
) -> list[dict]:
    """Notify a parent that a report card is ready through phone messaging."""
    try:
        cfg = config or _get_messaging_config()
    except ValueError as exc:
        logger.warning("SMS config missing, skipping report-available SMS: %s", exc)
        return [_skipped_result(provider=None, channel="sms", to=phone, reason=str(exc))]

    app_url = cfg["app_base_url"].rstrip("/")
    report_link = f"{app_url}/reports/{report_card_id}"
    body = (
        f"{student_name}'s report card for {term} is ready.\n"
        f"Log in to view it: {report_link}"
    )

    try:
        return send_sms_message(phone, body, cfg)
    except Exception as exc:
        logger.warning("Twilio report-available SMS failed for %s: %s", phone, exc)
        return [_failed_result(provider=cfg["provider"], channel="sms", to=phone, error=str(exc))]


def send_grades_available_sms(
    phone: str,
    student_name: str,
    course_name: str,
    term: str,
    config: dict | None = None,
) -> list[dict]:
    """Notify a parent that grades have been recorded through phone messaging."""
    try:
        cfg = config or _get_messaging_config()
    except ValueError as exc:
        logger.warning("SMS config missing, skipping grades-available SMS: %s", exc)
        return [_skipped_result(provider=None, channel="sms", to=phone, reason=str(exc))]

    app_url = cfg["app_base_url"].rstrip("/")
    body = (
        f"De nouvelles notes ont été enregistrées pour {student_name} en {course_name} ({term}).\n"
        f"/ New grades recorded for {student_name} in {course_name} ({term}).\n"
        f"Connectez-vous / Log in: {app_url}"
    )

    try:
        return send_sms_message(phone, body, cfg)
    except Exception as exc:
        logger.warning("Twilio grades-available SMS failed for %s: %s", phone, exc)
        return [_failed_result(provider=cfg["provider"], channel="sms", to=phone, error=str(exc))]
