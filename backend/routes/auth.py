from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import get_db
from limiter import limiter
from models import User
from schemas import ChangePasswordRequest, UserResponse


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

        email = payload.get("email")
        password = payload.get("password")
    elif "application/x-www-form-urlencoded" in content_type:
        body = (await request.body()).decode("utf-8")
        form_data = parse_qs(body, keep_blank_values=True)
        email = form_data.get("username", [""])[0]
        password = form_data.get("password", [""])[0]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login requires JSON or form-encoded request body",
        )

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Login requires email/username and password",
        )

    return str(email), str(password)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    email, password = await read_login_credentials(request)

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
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
