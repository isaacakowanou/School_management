"""Perform administrator-initiated parent and teacher password resets.

Stage a temporary password, forced-change flag, and token-version increment,
attempt delivery, then audit and commit the account changes.
Audit entries contain delivery outcomes but no plaintext password; the temporary
password is returned to the admin for handoff, and delivery currently precedes
the database commit.
"""

import secrets

from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import hash_password, invalidate_user_sessions
from models import Parent, Teacher, User
from services.email_service import send_temporary_password_reset_email
from services.sms_service import send_temporary_password_reset_sms


def reset_profile_password(
    db: Session,
    *,
    profile: Parent | Teacher,
    actor: User,
    entity_type: str,
) -> dict:
    """Reset a parent's or teacher's password for the requesting admin and return delivery results.

    Stage a generated password, forced-change flag, and token-version bump; attempt
    email or SMS, then audit and commit. Delivery currently happens before commit.
    The response includes the temporary password for admin handoff, but the audit
    entry records delivery outcomes without that secret.
    """
    temp_password = secrets.token_urlsafe(9)
    user = profile.user
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    invalidate_user_sessions(user)

    email_sent = None
    sms_sent = None
    if user.email:
        try:
            email_sent = bool(
                send_temporary_password_reset_email(
                    name=user.name, to_email=user.email, temp_password=temp_password
                ).get("success")
            )
        except Exception:
            email_sent = False
    elif profile.phone:
        try:
            results = send_temporary_password_reset_sms(
                name=user.name, phone=profile.phone, temp_password=temp_password
            )
            sms_sent = any(result.get("success") for result in results)
        except Exception:
            sms_sent = False

    # Never include temp_password in durable audit data: audit readers are more
    # numerous and logs generally have a longer retention period than secrets.
    create_audit_log(
        db=db,
        actor_user_id=actor.id,
        action="admin_password_reset",
        entity_type=entity_type,
        entity_id=profile.id,
        new_value={
            "target_user_id": user.id,
            "target_role": user.role,
            "email_sent": email_sent,
            "sms_sent": sms_sent,
        },
    )
    db.commit()
    return {
        "temp_password": temp_password,
        "email_sent": email_sent,
        "sms_sent": sms_sent,
    }
