"""Authentication lifecycle routes for login, profiles, and password recovery.

Login supports email, teacher employee number, and parent phone while preserving
anti-enumeration: unknown accounts, bad passwords, and missing or trashed role
profiles receive the same generic failure. Voluntary password changes require
the current password; forced first-login changes and OTP/email resets do not
because the temporary password, OTP, or reset token has just established
identity. Every successful password event increments ``token_version`` so old
JWTs stop working. Email recovery also returns the same response for known,
unknown, missing-profile, and trashed-profile accounts; invalid role profiles
receive no token and no email.
"""

import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import (
    create_user_access_token,
    get_current_user,
    hash_password,
    invalidate_user_sessions,
    verify_password,
)
from database import get_db
from limiter import limiter
from models import Parent, Teacher, User
from schemas import AccountProfileResponse, AccountProfileUpdate, ChangePasswordRequest, UserResponse, validate_password_strength
from services.email_service import send_password_reset_email
from services.password_reset_tokens import cleanup_reset_tokens, get_valid_reset_token, has_active_reset_token, issue_reset_token
from services.sms_service import check_otp, send_otp

logger = logging.getLogger(__name__)


router = APIRouter(tags=["auth"])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    user_id: UUID
    must_change_password: bool


class ChangePasswordResponse(BaseModel):
    status: str
    message: str
    access_token: str
    token_type: str


def _identifier_type(identifier: str) -> str:
    clean = identifier.strip()
    if "@" in clean:
        return "email"
    if clean.startswith("+") or clean.replace("-", "").replace(" ", "").isdigit():
        return "phone"
    return "employee_number"


def _profile_is_active(user: User, db: Session) -> bool:
    if user.role == "teacher":
        profile = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        return profile is not None and profile.deleted_at is None
    if user.role == "parent":
        profile = db.scalar(select(Parent).where(Parent.user_id == user.id))
        return profile is not None and profile.deleted_at is None
    return True


async def read_login_credentials(request: Request) -> tuple[str, str]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON request body",
            ) from exc

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON login body must be an object",
            )

        # Accept "identifier" (new) or "email" (legacy key) from JSON clients.
        identifier = payload.get("identifier") or payload.get("email")
        password = payload.get("password")
    elif "application/x-www-form-urlencoded" in content_type:
        body = (await request.body()).decode("utf-8")
        form_data = parse_qs(body, keep_blank_values=True)
        identifier = form_data.get("username", [""])[0]
        password = form_data.get("password", [""])[0]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login requires JSON or form-encoded request body",
        )

    if not identifier or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Login requires identifier and password",
        )

    return str(identifier), str(password)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    identifier, password = await read_login_credentials(request)

    # 1. Email lookup (works for admins and emailed teachers/parents).
    user = db.scalar(select(User).where(User.email == identifier))

    # 2. Teacher employee_number lookup.
    if user is None:
        teacher = db.scalar(
            select(Teacher)
            .join(Teacher.user)
            .where(Teacher.employee_number == identifier, Teacher.deleted_at.is_(None))
        )
        if teacher is not None:
            user = teacher.user

    # 3. Parent phone lookup.
    if user is None:
        parent = db.scalar(
            select(Parent)
            .join(Parent.user)
            .where(Parent.phone == identifier, Parent.deleted_at.is_(None))
        )
        if parent is not None:
            user = parent.user

    profile = None
    if user is not None and user.role == "teacher":
        profile = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    elif user is not None and user.role == "parent":
        profile = db.scalar(select(Parent).where(Parent.user_id == user.id))

    # A specific role-profile response would disclose account state. Missing and
    # trashed profiles stay indistinguishable from unknown users and bad passwords.
    role_profile_missing = user is not None and user.role in {"teacher", "parent"} and profile is None
    if (
        user is None
        or role_profile_missing
        or (profile is not None and profile.deleted_at is not None)
        or not verify_password(password, user.password_hash)
    ):
        create_audit_log(
            db=db,
            actor_user_id=None,
            action="auth_login_failed",
            entity_type="auth",
            entity_id=uuid.uuid4(),
            new_value={"identifier_type": _identifier_type(identifier)},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    create_audit_log(
        db=db,
        actor_user_id=user.id,
        action="auth_login_succeeded",
        entity_type="auth",
        entity_id=user.id,
        new_value={"role": user.role},
    )
    db.commit()
    access_token = create_user_access_token(user)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        user_id=user.id,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        must_change_password=current_user.must_change_password,
    )


@router.get("/profile", response_model=AccountProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountProfileResponse:
    phone = None
    if current_user.role == "teacher":
        profile = db.scalar(select(Teacher).where(Teacher.user_id == current_user.id))
        phone = profile.phone if profile else None
    elif current_user.role == "parent":
        profile = db.scalar(select(Parent).where(Parent.user_id == current_user.id))
        phone = profile.phone if profile else None
    return AccountProfileResponse(name=current_user.name, email=current_user.email, phone=phone, role=current_user.role)


@router.put("/profile", response_model=AccountProfileResponse)
def update_profile(
    payload: AccountProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountProfileResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name cannot be empty")
    current_user.name = name
    phone = None
    if current_user.role == "teacher":
        profile = db.scalar(select(Teacher).where(Teacher.user_id == current_user.id))
        if profile:
            profile.phone = (payload.phone or "").strip() or None
            phone = profile.phone
    elif current_user.role == "parent":
        profile = db.scalar(select(Parent).where(Parent.user_id == current_user.id))
        if profile:
            profile.phone = (payload.phone or "").strip() or None
            phone = profile.phone
    db.commit()
    return AccountProfileResponse(name=current_user.name, email=current_user.email, phone=phone, role=current_user.role)


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    # Forced-change users authenticated with a temporary password moments ago;
    # requiring that same value again adds no proof. Voluntary changes must
    # verify the current password to protect unattended authenticated sessions.
    if not current_user.must_change_password:
        if not payload.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "current_password_required", "message": "Current password is required"},
            )
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "current_password_incorrect", "message": "Current password is incorrect"},
            )
    was_forced = current_user.must_change_password
    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    invalidate_user_sessions(current_user)
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="forced_password_change_completed" if was_forced else "password_changed",
        entity_type="auth",
        entity_id=current_user.id,
        new_value={"role": current_user.role},
    )
    db.commit()
    # The version bump invalidates the request's JWT too. Returning a freshly
    # versioned token preserves this device while disconnecting all others.
    return ChangePasswordResponse(
        status="ok",
        message="Password changed successfully",
        access_token=create_user_access_token(current_user),
        token_type="bearer",
    )


@router.post("/logout")
def logout(_: User = Depends(get_current_user)) -> dict[str, str]:
    # JWT logout is client-side token disposal; server-side global revocation is
    # reserved for password and profile-trash events via token_version.
    return {"status": "ok", "message": "Logged out"}


class ForgotPasswordRequest(BaseModel):
    identifier: str


class ResetPasswordRequest(BaseModel):
    identifier: str
    otp: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


def _resolve_phone_for_identifier(identifier: str, db: Session) -> str | None:
    """Return the phone number to send an OTP to, or None if no match.

    Lookup order: Parent by phone → Teacher by employee_number.
    Only active (non-deleted) records are considered.
    """
    clean = identifier.strip()
    if not clean:
        return None

    # 1. Try Parent by phone.
    parent = db.scalar(
        select(Parent)
        .join(Parent.user)
        .where(Parent.phone == clean, Parent.deleted_at.is_(None))
    )
    if parent is not None:
        return parent.phone

    # 2. Try Teacher by employee_number.
    teacher = db.scalar(
        select(Teacher)
        .join(Teacher.user)
        .where(Teacher.employee_number == clean, Teacher.deleted_at.is_(None))
    )
    if teacher is not None and teacher.phone:
        return teacher.phone

    return None


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    cleanup_reset_tokens(db)
    clean = payload.identifier.strip()
    identifier_type = _identifier_type(clean)
    if identifier_type == "email":
        user = db.scalar(select(User).where(User.email == clean))
        active_user = user if user is not None and _profile_is_active(user, db) else None
        create_audit_log(
            db=db,
            actor_user_id=active_user.id if active_user else None,
            action="email_password_reset_requested",
            entity_type="auth",
            entity_id=active_user.id if active_user else uuid.uuid4(),
            new_value={"identifier_type": "email"},
        )
        # Unknown/trashed users deliberately fall through to the identical
        # success response. One active token also prevents repeated requests
        # from flooding a real user's inbox.
        if active_user is not None and not has_active_reset_token(db, active_user):
            raw_token = issue_reset_token(db, active_user)
            try:
                send_password_reset_email(active_user.name, clean, raw_token)
            except Exception:
                logger.exception("Password-reset email send failed")
        db.commit()
    else:
        phone = _resolve_phone_for_identifier(clean, db)
        if phone:
            try:
                send_otp(phone)
            except Exception:
                logger.exception("OTP send failed for identifier type %s", identifier_type)

    return {
        "message": "If an account with that identifier exists, you will receive a code or link."
    }


class EmailResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


@router.post("/reset-password/email")
@limiter.limit("5/minute")
async def reset_password_by_email(
    request: Request,
    payload: EmailResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    token = get_valid_reset_token(db, payload.token)
    if token is None or not _profile_is_active(token.user, db):
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_reset_link", "message": "Invalid or expired reset link"},
        )
    user = token.user
    token.used_at = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    invalidate_user_sessions(user)
    create_audit_log(
        db=db,
        actor_user_id=user.id,
        action="email_password_reset_completed",
        entity_type="auth",
        entity_id=user.id,
        new_value={"role": user.role},
    )
    db.commit()
    return {"status": "ok", "message": "Password reset successfully"}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    cleanup_reset_tokens(db)
    phone = _resolve_phone_for_identifier(payload.identifier, db)
    if phone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid identifier or OTP",
        )

    if not check_otp(phone, payload.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid identifier or OTP",
        )

    # Look up the user so we can update their password.
    clean = payload.identifier.strip()
    parent = db.scalar(
        select(Parent)
        .join(Parent.user)
        .where(Parent.phone == clean, Parent.deleted_at.is_(None))
    )
    if parent is not None:
        user = parent.user
    else:
        teacher = db.scalar(
            select(Teacher)
            .join(Teacher.user)
            .where(Teacher.employee_number == clean, Teacher.deleted_at.is_(None))
        )
        user = teacher.user if teacher else None

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid identifier or OTP",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    invalidate_user_sessions(user)
    create_audit_log(
        db=db,
        actor_user_id=user.id,
        action="otp_password_reset_completed",
        entity_type="auth",
        entity_id=user.id,
        new_value={"role": user.role},
    )
    db.commit()

    return {"status": "ok", "message": "Password reset successfully"}
