from uuid import UUID

from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str


class StatusResponse(BaseModel):
    status: str
    message: str
