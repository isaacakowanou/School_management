from datetime import date, datetime
from typing import Any
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


class TeacherCreate(BaseModel):
    user_id: UUID
    employee_number: str


class TeacherUpdate(BaseModel):
    employee_number: str


class TeacherResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    employee_number: str


class CourseResponse(BaseModel):
    id: UUID
    name: str
    code: str
    teacher_id: UUID
    grade_level: str
    term: str
    school_year: str


class CourseCreate(BaseModel):
    name: str
    code: str
    teacher_id: UUID
    grade_level: str
    term: str
    school_year: str


class CourseUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    teacher_id: UUID | None = None
    grade_level: str | None = None
    term: str | None = None
    school_year: str | None = None


class EnrollmentCreate(BaseModel):
    student_id: UUID
    course_id: UUID


class EnrollmentResponse(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID


class GradeItemCreate(BaseModel):
    course_id: UUID
    title: str
    category: str
    max_score: float
    weight: float
    term: str
    due_date: date | None = None


class GradeItemUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    max_score: float | None = None
    weight: float | None = None
    term: str | None = None
    due_date: date | None = None


class GradeItemResponse(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    category: str
    max_score: float
    weight: float
    term: str
    due_date: date | None = None


class GradeCreate(BaseModel):
    student_id: UUID
    grade_item_id: UUID
    score: float


class GradeUpdate(BaseModel):
    score: float


class GradeResponse(BaseModel):
    id: UUID
    student_id: UUID
    grade_item_id: UUID
    course_id: UUID
    score: float
    submitted_by_teacher_id: UUID


class CourseResultResponse(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID
    term: str
    average: float
    letter_grade: str


class SkippedCourseResultStudent(BaseModel):
    student_id: UUID
    student_name: str
    missing_grade_items: list[str]


class CourseResultCalculationResponse(BaseModel):
    course_id: UUID
    term: str
    calculated_count: int
    skipped_students: list[SkippedCourseResultStudent]
    results: list[CourseResultResponse]


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    created_at: datetime


class ReportGenerateRequest(BaseModel):
    term: str
    school_year: str


class ReportReviewUpdate(BaseModel):
    ai_summary: str | None = None


class ReportCardCourseResponse(BaseModel):
    id: UUID
    course_id: UUID
    course_name: str
    average: float
    letter_grade: str


class ReportCardResponse(BaseModel):
    id: UUID
    student_id: UUID
    term: str
    school_year: str
    overall_average: float
    gpa: float | None = None
    status: str
    ai_summary: str | None = None
    pdf_url: str | None = None
    courses: list[ReportCardCourseResponse]


class AdminReportListItem(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    student_number: str
    term: str
    school_year: str
    status: str
    overall_average: float
    gpa: float | None = None
    created_at: datetime
    needs_review: bool


class ReportCardStalenessResponse(BaseModel):
    is_stale: bool
    reason: str
    snapshot_overall_average: float
    current_overall_average: float | None = None
    snapshot_gpa: float | None = None
    current_gpa: float | None = None


class ReportSendResponse(BaseModel):
    report_card_id: UUID
    status: str
    sent_count: int
    failed_count: int
    results: list[dict[str, Any]]


class AIWarningResponse(BaseModel):
    warning_type: str
    message: str
    severity: str
    entity_type: str | None = None
    entity_id: UUID | None = None


class AISummaryResponse(BaseModel):
    report_card_id: UUID
    ai_summary: str
