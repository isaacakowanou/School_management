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


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    grade_level: str
    student_number: str


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    grade_level: str | None = None
    student_number: str | None = None


class StudentResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    grade_level: str
    student_number: str


class StudentParentLinkCreate(BaseModel):
    parent_id: UUID
    relationship: str | None = None


class LinkedParentResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    phone: str | None = None
    relationship: str | None = None


class ParentCreate(BaseModel):
    user_id: UUID
    phone: str | None = None


class ParentUpdate(BaseModel):
    phone: str | None = None


class ParentResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    phone: str | None = None
