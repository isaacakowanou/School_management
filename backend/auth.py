"""Provide password/JWT helpers and enforce session checks on every authenticated request.

Reject weak/default signing secrets unless local/test mode is explicitly selected,
and verify signature, expiry, database user, and token_version before access.
Deleted users and missing or deleted parent/teacher profiles are rejected;
hard deletion also invalidates tokens because the user lookup fails.
Forced-password-change sessions may use only the explicit account endpoints,
and role guards use the database role rather than trusting the browser.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Parent, Teacher, User


DEFAULT_JWT_SECRET_KEY = "change-me-before-production"
APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEFAULT_JWT_SECRET_KEY).strip() or DEFAULT_JWT_SECRET_KEY
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Only an explicit local/test mode permits the development signing key.
# Unset, misspelled, and deployment-specific environment names fail closed.
if APP_ENV not in {"local", "test"} and (
    JWT_SECRET_KEY == DEFAULT_JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32
):
    raise RuntimeError(
        "JWT_SECRET_KEY must be a non-default secret of at least 32 characters; "
        "only explicit APP_ENV=local or APP_ENV=test permits development credentials"
    )

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the supplied plaintext password for storage."""
    return password_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches the stored bcrypt hash."""
    return password_context.verify(plain_password, password_hash)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Sign a JWT for the given subject, expiry interval, and optional extra claims.

    The default expiry comes from configuration. Extra claims are merged last;
    callers are responsible for supplying trusted claim values.
    """
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_user_access_token(user: User) -> str:
    """Return a signed session token carrying this user's ID, role, and token version."""
    return create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "ver": user.token_version},
    )


def invalidate_user_sessions(user: User) -> None:
    # Versioning invalidates every previously issued JWT without storing tokens.
    """Increment the user's token version in memory, invalidating old JWTs once committed.

    The caller owns the database transaction; this function does not commit.
    """
    user.token_version += 1


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify a JWT's signature and expiry and return its claims.

    Only the configured signing algorithm is accepted. Invalid tokens raise 401;
    user existence and token-version checks happen in get_current_user.
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a usable database user or reject the request.

    Check signature, expiry, user deletion, token version, and the existence of an
    active parent/teacher profile on every call. A forced password change allows
    only the explicit account-recovery endpoints, not ordinary school data.
    Deleting the user also kills old JWTs because the subject lookup then fails.
    """
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, user_uuid)
    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Do not accept legacy/versionless tokens: password resets and trash events
    # rely on this exact comparison to terminate all earlier sessions.
    if payload.get("ver") != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    profile = None
    if user.role == "teacher":
        profile = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    elif user.role == "parent":
        profile = db.scalar(select(Parent).where(Parent.user_id == user.id))
    # Login-time filtering is insufficient because a profile may be trashed or
    # purged after a JWT was issued. Admin users intentionally have no profile;
    # parent/teacher users require one for the account to remain valid.
    role_profile_missing = user.role in {"teacher", "parent"} and profile is None
    if role_profile_missing or (profile is not None and profile.deleted_at is not None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Keep this allowlist narrow. must_change_password is enforced here so API
    # clients cannot bypass the frontend's first-login redirect.
    forced_change_exemptions = {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/change-password"),
        ("POST", "/api/v1/auth/logout"),
    }
    if user.must_change_password and (request.method, request.url.path) not in forced_change_exemptions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "password_change_required",
                "message": "Password change required",
            },
        )

    return user


def require_role(required_role: str):
    """Return a FastAPI dependency that requires the given database role.

    It resolves the current user through the full session checks, then returns
    that user or raises 403; it does not trust a role supplied by the browser.
    """
    def role_guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_guard


require_admin = require_role("admin")
require_teacher = require_role("teacher")
require_parent = require_role("parent")
