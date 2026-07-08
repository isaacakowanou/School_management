from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    return value


class SchoolLevel(str, Enum):
    maternelle = "maternelle"
    primaire = "primaire"
    college = "college"


class LanguageGroup(str, Enum):
    FRENCH = "FRENCH"
    ENGLISH = "ENGLISH"


class TrimesterTerm(str, Enum):
    # Canonical GGFK trimester values (A1.7c). Single source of truth for the
    # term dropdowns; mirrors constants.TRIMESTER_TERMS (list position ==
    # trimester number). Free-text terms are rejected at every write path.
    FIRST = "1er Trimestre"
    SECOND = "2ème Trimestre"
    THIRD = "3ème Trimestre"


class SubjectLevelGroup(str, Enum):
    NURSERY = "NURSERY"
    PRIMARY = "PRIMARY"
    COLLEGE_FIRST_CYCLE = "COLLEGE_FIRST_CYCLE"
    COLLEGE_SECOND_CYCLE = "COLLEGE_SECOND_CYCLE"


class GradeItemType(str, Enum):
    INTERRO = "INTERRO"
    DEVOIR = "DEVOIR"
    COMPOSITION = "COMPOSITION"


class LetterGrade(str, Enum):
    # BISC 9-letter grade codes (A1.3). Single source of truth for the conduct /
    # work-habit dropdowns; the frontend constant mirrors these values.
    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C_PLUS = "C+"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None


class ChangePasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str | None = None
    role: str
    must_change_password: bool = False


class StatusResponse(BaseModel):
    status: str
    message: str


class DangerZonePreviewResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    target_label: str
    counts: dict[str, int]
    warnings: list[str] = []


class DangerZoneSearchResult(BaseModel):
    id: UUID
    label: str
    subtitle: str
    entity_type: str


class DangerZoneDeleteRequest(BaseModel):
    entity_type: str
    entity_id: UUID
    confirmation: str
    reason: str | None = None


class DangerZoneDeleteResponse(BaseModel):
    status: str
    batch_id: UUID
    target_label: str
    counts: dict[str, int]


class DangerZoneBatchResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    target_label: str
    reason: str | None = None
    deleted_by_user_id: UUID
    deleted_at: datetime
    restored_at: datetime | None = None
    restored_by_user_id: UUID | None = None
    counts: dict[str, int]


class ClassCreate(BaseModel):
    name_fr: str
    name_en: str | None = None
    school_level: SchoolLevel
    stream: str | None = None
    sort_order: int
    school_year: str


class ClassUpdate(BaseModel):
    name_fr: str | None = None
    name_en: str | None = None
    school_level: SchoolLevel | None = None
    stream: str | None = None
    sort_order: int | None = None
    school_year: str | None = None


class ClassResponse(BaseModel):
    id: UUID
    name_fr: str
    name_en: str | None = None
    school_level: SchoolLevel
    stream: str | None = None
    sort_order: int
    school_year: str
    student_count: int = 0
    course_count: int = 0


class ClassBulkCreateRequest(BaseModel):
    school_year: str


class ClassBulkCreateResponse(BaseModel):
    status: str
    # Canonical name_fr of taxonomy classes created for the year vs. skipped
    # because a (normalized-name) match already existed.
    created: list[str]
    skipped: list[str]


class ClassEnrollmentPreviewResponse(BaseModel):
    # "ok" when both sides have >=1 row; "empty" when either is 0 (no writes
    # would happen). Callers show a specific message using the two counts.
    status: str
    class_id: UUID
    school_year: str
    students_in_class: int
    # Distinct courses tagged with this class AND matching class.school_year.
    courses_in_class: int
    enrollments_to_create: int
    enrollments_already_existing: int


class ClassBulkEnrollResponse(BaseModel):
    status: str
    class_id: UUID
    school_year: str
    students_in_class: int
    courses_in_class: int
    enrollments_created: int
    enrollments_skipped: int


class SubjectCreate(BaseModel):
    name_fr: str
    name_en: str
    # Bulletin section; reuses LanguageGroup because the values are the same
    # thing — a course created from this subject inherits it as language_group.
    section: LanguageGroup
    level_group: SubjectLevelGroup
    sort_order: int
    applicable_classes: list[str] | None = None


class SubjectUpdate(BaseModel):
    name_fr: str | None = None
    name_en: str | None = None
    section: LanguageGroup | None = None
    level_group: SubjectLevelGroup | None = None
    sort_order: int | None = None
    applicable_classes: list[str] | None = None


class SubjectResponse(BaseModel):
    id: UUID
    name_fr: str
    name_en: str
    section: LanguageGroup
    level_group: SubjectLevelGroup
    sort_order: int
    applicable_classes: list[str] | None = None
    course_count: int = 0


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    school_level: SchoolLevel | None = None
    student_number: str | None = None
    educmaster_number: str | None = None
    class_id: UUID | None = None


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    school_level: SchoolLevel | None = None
    student_number: str | None = None
    educmaster_number: str | None = None
    class_id: UUID | None = None


class StudentResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    school_level: SchoolLevel | None = None
    student_number: str
    educmaster_number: str | None = None
    class_id: UUID | None = None
    class_name: str | None = None


class DeletedStudentResponse(StudentResponse):
    deleted_at: datetime


class StudentParentLinkCreate(BaseModel):
    parent_id: UUID
    relationship: str | None = None


class LinkedParentResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    relationship: str | None = None


class ParentCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None


class ParentUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class ParentSelfUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None


class ParentResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str | None = None
    phone: str | None = None


class ParentCreateResponse(ParentResponse):
    temp_password: str
    # Whether the account-created notification went out. None = not attempted
    # (no email/phone on the account); False = attempted but failed, so the
    # admin must hand the temp password over directly.
    email_sent: bool | None = None
    sms_sent: bool | None = None


class TeacherCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    employee_number: str | None = None


class TeacherUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    employee_number: str | None = None


class TeacherResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    employee_number: str


class TeacherCreateResponse(TeacherResponse):
    temp_password: str
    # Same semantics as ParentCreateResponse: None = not attempted,
    # False = attempted but failed (admin must share the password directly).
    email_sent: bool | None = None
    sms_sent: bool | None = None


class CourseResponse(BaseModel):
    id: UUID
    name: str
    code: str
    teacher_id: UUID
    term: str
    school_year: str
    language_group: LanguageGroup | None = None
    class_id: UUID | None = None
    class_name: str | None = None
    class_school_level: str | None = None
    subject_id: UUID | None = None
    coefficient: int = 1


class CourseCreate(BaseModel):
    # Optional when subject_id is provided (the route derives name from the
    # subject); still required for free-text courses — enforced in the route.
    name: str | None = None
    code: str
    teacher_id: UUID
    term: TrimesterTerm
    school_year: str
    language_group: LanguageGroup | None = None
    class_id: UUID | None = None
    subject_id: UUID | None = None
    # ge=1: a zero coefficient silently drops the course from the class
    # average and a negative one corrupts it.
    coefficient: int = Field(default=1, ge=1)


class CourseUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    teacher_id: UUID | None = None
    term: TrimesterTerm | None = None
    school_year: str | None = None
    language_group: LanguageGroup | None = None
    class_id: UUID | None = None
    subject_id: UUID | None = None
    coefficient: int | None = Field(default=None, ge=1)


class CourseCloneYearRequest(BaseModel):
    source_year: str
    target_year: str


class CourseCloneYearResponse(BaseModel):
    status: str
    created_count: int
    # Source class names that had no same-named class in the target year; the
    # cloned courses were created with class_id null.
    unmatched_class_names: list[str]


class TermAdvanceRequest(BaseModel):
    school_year: str
    target_term: TrimesterTerm


class TermAdvanceCoursePreview(BaseModel):
    course_id: UUID
    code: str
    name: str
    current_term: str
    already_on_target: bool
    enrolled_count: int
    # CourseResults calculated for the course's CURRENT term (the one being
    # closed) — enrolled_count vs this count shows how complete the term is.
    results_calculated_count: int
    # Machine-readable warning keys the frontend translates:
    # missing_interro / missing_devoir / missing_composition (Beninese-mode
    # closing-term completeness) and non_canonical_term.
    warnings: list[str]


class TermAdvancePreviewResponse(BaseModel):
    school_year: str
    target_term: str
    courses: list[TermAdvanceCoursePreview]
    total_count: int
    already_on_target_count: int


class TermAdvanceResponse(BaseModel):
    status: str
    school_year: str
    target_term: str
    updated_count: int
    skipped_count: int


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
    # Null for Beninese-mode items; required for weighted-mode items (enforced
    # in the route after mode detection).
    category: str | None = None
    # Defaults to the /20 scale; teachers can still set a custom max (e.g. 10).
    max_score: float = 20
    # Null for Beninese-mode items (weight is meaningless); required for
    # weighted-mode items — enforced in the route after mode detection.
    weight: float | None = None
    # INTERRO / DEVOIR / COMPOSITION for Beninese-mode courses; null (or
    # omitted) for weighted-mode courses.
    item_type: GradeItemType | None = None
    term: TrimesterTerm
    due_date: date | None = None


class GradeItemUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    max_score: float | None = None
    weight: float | None = None
    # item_type is immutable after creation — the route rejects any non-null value.
    item_type: GradeItemType | None = None
    term: TrimesterTerm | None = None
    due_date: date | None = None


class GradeItemResponse(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    category: str | None = None
    max_score: float
    weight: float | None = None
    item_type: str | None = None
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


class NotifyGradesPayload(BaseModel):
    student_ids: list[UUID]


class CourseResultResponse(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID
    term: str
    average: float
    letter_grade: str
    # Grade scale of average: "20" for results calculated after the A1.2 switch,
    # "100" for historical results not yet recalculated.
    scale: str = "20"
    # Beninese formula intermediates — null for weighted-mode results.
    moy_int: float | None = None
    mcc: float | None = None
    devoir_score: float | None = None
    composition_score: float | None = None


class CourseResultCalculationRequest(BaseModel):
    student_ids: list[UUID]


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
    actor_name: str | None = None
    actor_email: str | None = None
    action: str
    entity_type: str
    entity_id: UUID
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    created_at: datetime


class ReportGenerateRequest(BaseModel):
    term: TrimesterTerm
    school_year: str


class ReportReviewUpdate(BaseModel):
    ai_summary: str | None = None


class ReportCardCourseResponse(BaseModel):
    id: UUID
    course_id: UUID
    course_name: str
    average: float
    letter_grade: str
    coefficient: int = 1
    moy_int: float | None = None
    mcc: float | None = None
    devoir_score: float | None = None
    composition_score: float | None = None


class ReportItemResponse(BaseModel):
    item_key: str
    label_en: str
    label_fr: str
    letter_grade: LetterGrade | None = None


class ReportItemUpdate(BaseModel):
    item_key: str
    letter_grade: LetterGrade | None = None


class ReportCardResponse(BaseModel):
    id: UUID
    student_id: UUID
    term: str
    school_year: str
    overall_average: float
    french_average: float | None = None
    english_average: float | None = None
    bilingual_average: float | None = None
    gpa: float | None = None
    # Grade scale of overall_average and course averages: "20" or "100".
    scale: str = "20"
    status: str
    ai_summary: str | None = None
    teacher_comment_fr: str | None = None
    teacher_comment_en: str | None = None
    principal_comment_fr: str | None = None
    principal_comment_en: str | None = None
    pdf_url: str | None = None
    courses: list[ReportCardCourseResponse]
    conduct_items: list[ReportItemResponse] = []
    work_habit_items: list[ReportItemResponse] = []


class AdminReportCardResponse(ReportCardResponse):
    student_name: str
    student_number: str


class ReportDetailsUpdate(BaseModel):
    conduct_items: list[ReportItemUpdate] | None = None
    work_habit_items: list[ReportItemUpdate] | None = None
    teacher_comment_fr: str | None = None
    teacher_comment_en: str | None = None
    principal_comment_fr: str | None = None
    principal_comment_en: str | None = None


class AdminReportListItem(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    student_number: str
    term: str
    school_year: str
    status: str
    overall_average: float
    bilingual_average: float | None = None
    gpa: float | None = None
    # Grade scale of overall_average: "20" or "100" (historical reports).
    scale: str = "20"
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


class ClassReportBatchRequest(BaseModel):
    class_id: UUID
    school_year: str
    term: TrimesterTerm


class ClassReportStatusRow(BaseModel):
    student_id: UUID
    student_name: str
    student_number: str
    # CourseResults calculated for this student in (term, school_year) —
    # 0 means batch-generate would skip them with no_results.
    results_count: int
    # Null report_id means no report card exists yet for this term+year.
    report_id: UUID | None = None
    report_status: str | None = None
    overall_average: float | None = None
    french_average: float | None = None
    english_average: float | None = None
    bilingual_average: float | None = None
    needs_review: bool = False


class ClassReportStatusResponse(BaseModel):
    class_id: UUID
    class_name: str
    school_year: str
    term: str
    students: list[ClassReportStatusRow]
    total_students: int
    without_report_count: int
    draft_count: int
    approved_count: int
    sent_count: int
    needs_review_count: int


class ClassReportBatchGenerateResponse(BaseModel):
    status: str
    generated_count: int
    skipped_existing_count: int
    skipped_no_results_count: int
    report_ids: list[UUID]


class ClassReportBatchApproveResponse(BaseModel):
    status: str
    approved_count: int
    skipped_count: int


class ClassReportBatchSendResponse(BaseModel):
    status: str
    sent_count: int
    failed_count: int
    no_recipient_count: int


class ClassPdfJobResponse(BaseModel):
    job_id: UUID
    # pending -> done | failed. The status endpoint returns the PDF itself
    # once done, so this JSON shape is only seen while pending or failed.
    status: str
    error: str | None = None
    report_count: int | None = None


class AIWarningResponse(BaseModel):
    warning_type: str
    message: str
    severity: str
    entity_type: str | None = None
    entity_id: UUID | None = None


class AISummaryResponse(BaseModel):
    report_card_id: UUID
    ai_summary: str
