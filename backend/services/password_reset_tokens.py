"""Issue and check single-use email password-reset links.

Store only SHA-256 token digests, with a 45-minute expiry and the user's token
version so another password event invalidates old links. Issuance replaces
unused tokens and helpers stage lazy cleanup in the caller's transaction.
Routes check account eligibility, consume valid tokens, and commit the changes.
"""

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
    # The raw bearer secret exists only in the email URL; compare its digest.
    """Return the SHA-256 digest used to look up a raw email reset token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def cleanup_reset_tokens(db: Session) -> None:
    """Delete expired or consumed reset-token rows in the caller's transaction.

    No commit is performed; callers decide whether to persist this lazy cleanup.
    """
    now = _now()
    db.execute(
        delete(PasswordResetToken).where(
            (PasswordResetToken.expires_at < now) | PasswordResetToken.used_at.is_not(None)
        )
    )


def issue_reset_token(db: Session, user: User) -> str:
    """Stage one new 45-minute reset token for the user and return its raw secret.

    Remove prior unused tokens and store only the new digest and current token
    version. The caller must commit before relying on the emailed link.
    """
    cleanup_reset_tokens(db)
    # One unused token per user limits inbox flooding and makes the newest
    # recovery attempt the only credential worth retaining.
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
    """Return whether the user has an unused, unexpired token for their current version.

    Expired/used rows are cleaned up in the session, without committing.
    """
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
    """Return the matching unused, unexpired reset-token row, or None.

    Check the saved token version against the user's current version. This may
    stage cleanup deletions but neither consumes the valid token nor commits it;
    the route must also enforce the account's active status.
    """
    cleanup_reset_tokens(db)
    token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(raw_token))
    )
    if token is None or token.used_at is not None:
        return None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    # Version binding revokes an emailed link after any other password reset or
    # change, even when the link itself has not expired or been consumed.
    if expires_at <= _now() or token.token_version != token.user.token_version:
        return None
    return token
