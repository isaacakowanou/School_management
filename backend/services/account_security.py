"""Security-sensitive account operations initiated by an administrator.

An admin reset installs a generated temporary password, forces a first-login
change, and increments ``token_version`` so every existing target-user session
ends immediately. Delivery outcomes, but never the temporary password, are
recorded in the audit log; the password is returned only to the calling admin
for the existing credential handoff workflow.
"""

import secrets

from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import hash_password, invalidate_user_sessions
from models import Parent, Teacher, User
from services.email_service import send_account_created_email
from services.sms_service import send_account_created_sms


def reset_profile_password(
    db: Session,
    *,
    profile: Parent | Teacher,
    actor: User,
    entity_type: str,
) -> dict:
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
                send_account_created_email(
                    name=user.name, to_email=user.email, temp_password=temp_password
                ).get("success")
            )
        except Exception:
            email_sent = False
    elif profile.phone:
        try:
            results = send_account_created_sms(
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
