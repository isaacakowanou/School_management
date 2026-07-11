import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models import PasswordResetToken, User


RESET_TOKEN_LIFETIME_MINUTES = 45


def _now() -> datetime:
    return datetime.now(timezone.utc)


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def cleanup_reset_tokens(db: Session) -> None:
    now = _now()
    db.execute(
        delete(PasswordResetToken).where(
            (PasswordResetToken.expires_at < now) | PasswordResetToken.used_at.is_not(None)
        )
    )


def issue_reset_token(db: Session, user: User) -> str:
    cleanup_reset_tokens(db)
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_digest(raw_token),
            token_version=user.token_version,
            expires_at=_now() + timedelta(minutes=RESET_TOKEN_LIFETIME_MINUTES),
        )
    )
    return raw_token


def has_active_reset_token(db: Session, user: User) -> bool:
    cleanup_reset_tokens(db)
    return db.scalar(
        select(PasswordResetToken.id).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > _now(),
            PasswordResetToken.token_version == user.token_version,
        )
    ) is not None


def get_valid_reset_token(db: Session, raw_token: str) -> PasswordResetToken | None:
    cleanup_reset_tokens(db)
    token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(raw_token))
    )
    if token is None or token.used_at is not None:
        return None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now() or token.token_version != token.user.token_version:
        return None
    return token
