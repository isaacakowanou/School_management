import logging
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import get_db
from limiter import limiter
from models import Parent, Teacher, User
from schemas import ChangePasswordRequest, UserResponse
from services.sms_service import check_otp, send_otp

logger = logging.getLogger(__name__)


router = APIRouter(tags=["auth"])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    user_id: UUID
    must_change_password: bool


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

    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id), extra_claims={"role": user.role})
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


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    return {"status": "ok", "message": "Password changed successfully"}


@router.post("/logout")
def logout(_: User = Depends(get_current_user)) -> dict[str, str]:
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
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


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
    # No user-enumeration: always return 200 regardless of whether we found a match.
    # Email-based reset is deferred — users with email contact admin to reset.
    phone = _resolve_phone_for_identifier(payload.identifier, db)
    if phone:
        try:
            send_otp(phone)
        except Exception:
            logger.exception("OTP send failed for identifier %r", payload.identifier)

    return {
        "message": "If an account with that identifier exists, you will receive a code."
    }


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
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
    db.commit()

    return {"status": "ok", "message": "Password reset successfully"}
