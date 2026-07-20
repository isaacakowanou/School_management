"""Authentication primitives and the server-side session security boundary.

JWTs carry the user's current ``token_version`` in a ``ver`` claim and are
accepted only while that claim matches the database. Every password event
increments the version, providing a global session kill without maintaining a
token denylist. The authenticated-user dependency also enforces forced password
changes and rejects missing or trashed teacher/parent profiles on every request;
frontend redirects and login-time checks are defense-in-depth, not the security
boundary. Hard-deleting a user invalidates every JWT independently of
``token_version`` because authenticated requests require the subject row.
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
APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEFAULT_JWT_SECRET_KEY).strip() or DEFAULT_JWT_SECRET_KEY
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if APP_ENV == "production" and JWT_SECRET_KEY == DEFAULT_JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY must be set to a non-default value when APP_ENV or ENVIRONMENT is production"
    )

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
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
    return create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "ver": user.token_version},
    )


def invalidate_user_sessions(user: User) -> None:
    # Versioning invalidates every previously issued JWT without storing tokens.
    user.token_version += 1


def decode_access_token(token: str) -> dict[str, Any]:
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
    if user is None:
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
