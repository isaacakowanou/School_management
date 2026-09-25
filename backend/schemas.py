"""Shared API schemas and closed vocabularies for security and grading.

All request models that can create or replace a password delegate to
``validate_password_strength``. Keeping the minimum length and non-whitespace
rule here prevents privileged update routes, forced changes, and recovery flows
from drifting into weaker policies than ordinary account creation.

Grading writes use closed enums for GGFK's three canonical trimesters,
Beninese Interro/Devoir/Composition item types, and nine letter grades. Keeping
these as schemas prevents new API writes from recreating the legacy free-text
term drift audited by ``scripts/count_legacy_terms.py``.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not value.strip():
        raise ValueError("Password must contain non-whitespace characters")
    return value


class SchoolLevel(str, Enum):
    maternelle = "maternelle"
    primaire = "primaire"
    college = "college"


class LanguageGroup(str, Enum):
    FRENCH = "FRENCH"
    ENGLISH = "ENGLISH"


class GradingSystem(str, Enum):
    BENINESE = "BENINESE"
    WEIGHTED = "WEIGHTED"


class TrimesterTerm(str, Enum):
    # Canonical GGFK trimester values (A1.7c). Single source of truth for the
    # term dropdowns; mirrors constants.TRIMESTER_TERMS (list position ==
    # trimester number). Free-text terms are rejected at every write path.
    FIRST = "1er Trimestre"
    SECOND = "2ème Trimestre"
    THIRD = "3ème Trimestre"


class TrimesterLockUpdate(BaseModel):
    school_year: str
    term: TrimesterTerm
    is_locked: bool


class TrimesterLockResponse(BaseModel):
    id: UUID | None = None
    school_year: str
    term: TrimesterTerm
    is_locked: bool
    updated_by_admin_id: UUID | None = None
    locked_at: datetime | None = None
    updated_at: datetime | None = None


class AcademicContextResponse(BaseModel):
    current_school_year: str | None
    current_term: str
    available_school_years: list[str]
    terms: list[str]


class SubjectLevelGroup(str, Enum):
    NURSERY = "NURSERY"
    PRIMARY = "PRIMARY"
    COLLEGE_FIRST_CYCLE = "COLLEGE_FIRST_CYCLE"
    COLLEGE_SECOND_CYCLE = "COLLEGE_SECOND_CYCLE"


class GradeItemType(str, Enum):
    # Notation béninoise is intentionally closed to these three Ministry
    # components. Weighted-course categories use ``category`` instead.
    INTERRO = "INTERRO"
    DEVOIR = "DEVOIR"
    COMPOSITION = "COMPOSITION"


class LetterGrade(str, Enum):
    # GGFK /20 nine-letter bands (A1.3). Conduct and work habits select these
    # codes directly; academic courses derive them from numeric /20 results.
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
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        return validate_password_strength(v) if v is not None else None


class ChangePasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str | None = None
    role: str
    must_change_password: bool = False


class AccountProfileResponse(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    role: str


class AccountProfileUpdate(BaseModel):
    name: str
    phone: str | None = None


class AdminPasswordResetResponse(BaseModel):
    temp_password: str
    email_sent: bool | None = None
    sms_sent: bool | None = None


class StatusResponse(BaseModel):
    status: str
    message: str


class AdminStatsCurrentTerm(BaseModel):
    name: str
    trimester: int


class AdminStatsBulletins(BaseModel):
    generated: int
    approved: int
    sent: int


class AdminStatsResponse(BaseModel):
    students: int
    teachers: int
    parents: int
    classes: int
    current_term: AdminStatsCurrentTerm | None = None
    bulletins: AdminStatsBulletins


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


class TrashEntryResponse(BaseModel):
    id: str
    source: str
    entity_type: str
    entity_id: UUID
    target_label: str
    deleted_at: datetime
    counts: dict[str, int]
    metadata: dict[str, str | None] = {}
    restored_at: datetime | None = None


class TrashListResponse(BaseModel):
    entries: list[TrashEntryResponse]
    summary: dict[str, int]
    retention_days: int


class TrashActionResponse(BaseModel):
    status: str
    message: str
    target_label: str | None = None
    counts: dict[str, int] = {}


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


class SchoolYearCreateRequest(BaseModel):
    school_year: str
    clone_courses: bool = False
    source_school_year: str | None = None


class SchoolYearCreateResponse(BaseModel):
    status: str
    school_year: str
    created_classes: list[str]
    skipped_classes: list[str]
    cloned_course_count: int = 0
    skipped_course_count: int = 0
    unmatched_class_names: list[str] = []
    source_school_year: str | None = None
    nothing_to_do: bool = False


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


class PassageDecisionValue(str, Enum):
    PASS = "pass"
    REPEAT = "repeat"
    GRADUATE = "graduate"


class PassageStudentRow(BaseModel):
    student_id: UUID
    student_name: str
    student_number: str
    current_class_id: UUID | None = None
    current_class_name: str | None = None
    annual_french_average: float | None = None
    annual_english_average: float | None = None
    annual_bilingual_average: float | None = None
    incomplete_data: bool
    missing_terms: list[str] = []
    suggested_decision: str
    suggested_reason: str
    requires_decision: bool
    existing_decision_id: UUID | None = None
    final_decision: str | None = None
    target_class_id: UUID | None = None
    target_class_name: str | None = None
    target_options: list[str] = []
    target_class_missing: bool = False
    note: str | None = None


class PassageClassPreviewResponse(BaseModel):
    class_id: UUID
    class_name: str
    school_year: str
    target_school_year: str
    target_classes_ready: bool
    missing_target_class_names: list[str] = []
    target_class_guidance: str | None = None
    students: list[PassageStudentRow]


class PassageConfirmEntry(BaseModel):
    student_id: UUID
    final_decision: PassageDecisionValue
    target_class_name: str | None = None
    note: str | None = None


class PassageConfirmRequest(BaseModel):
    school_year: str
    target_school_year: str
    class_id: UUID | None = None
    decisions: list[PassageConfirmEntry]


class PassageDecisionResponse(BaseModel):
    id: UUID
    student_id: UUID
    school_year: str
    target_school_year: str
    from_class_id: UUID | None = None
    from_class_name: str | None = None
    result_class_id: UUID | None = None
    result_class_name: str | None = None
    suggested_decision: str
    final_decision: str
    annual_french_average: float | None = None
    annual_english_average: float | None = None
    annual_bilingual_average: float | None = None
    incomplete_data: bool
    note: str | None = None
    decided_by_admin_id: UUID | None = None
    decided_at: datetime


class ParentPassageDecisionResponse(BaseModel):
    school_year: str
    from_class_name: str | None = None
    decision: str
    result_class_name: str | None = None


class PassageConfirmResponse(BaseModel):
    status: str
    applied_count: int
    decisions: list[PassageDecisionResponse]


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
    class_school_year: str | None = None


class StudentResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    school_level: SchoolLevel | None = None
    student_number: str
    educmaster_number: str | None = None
    class_id: UUID | None = None
    class_name: str | None = None
    academic_status: str = "active"
    historical_class_name: str | None = None
    assignment_school_year: str | None = None
    is_unassigned_for_year: bool = False


class StudentImportIssue(BaseModel):
    code: str
    field: str | None = None
    message: str


class StudentImportPreviewRow(BaseModel):
    row_number: int
    student_first_name: str
    student_last_name: str
    class_name: str
    parent_name: str
    parent_email: str
    student_number: str
    educmaster_number: str
    parent_phone: str
    relationship: str
    class_id: UUID | None = None
    school_level: SchoolLevel | None = None
    parent_action: str
    is_valid: bool
    errors: list[StudentImportIssue]
    warnings: list[StudentImportIssue]


class StudentImportPreviewResponse(BaseModel):
    school_year: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[StudentImportPreviewRow]


class StudentImportCommitRow(BaseModel):
    row_number: int
    status: str
    student_id: UUID | None = None
    student_number: str | None = None
    parent_id: UUID | None = None
    parent_action: str | None = None


class StudentImportFailure(BaseModel):
    row_number: int
    errors: list[StudentImportIssue]


class StudentImportEmailResult(BaseModel):
    parent_id: UUID
    email: str
    success: bool
    error: str | None = None
    temp_password: str | None = None


class StudentImportCommitResponse(BaseModel):
    status: str
    created: int
    failed: int
    parents_reused: int
    parents_created: int
    emails_sent: int
    emails_failed: int
    rows: list[StudentImportCommitRow]
    failures: list[StudentImportFailure]
    email_results: list[StudentImportEmailResult]


class TeacherImportIssue(BaseModel):
    code: str
    field: str | None = None
    message: str


class TeacherImportPreviewRow(BaseModel):
    row_number: int
    teacher_name: str
    teacher_email: str
    teacher_phone: str
    employee_number: str
    teacher_action: str
    is_valid: bool
    errors: list[TeacherImportIssue]
    warnings: list[TeacherImportIssue]


class TeacherImportPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[TeacherImportPreviewRow]


class TeacherImportCommitRow(BaseModel):
    row_number: int
    status: str
    teacher_id: UUID | None = None
    employee_number: str | None = None


class TeacherImportFailure(BaseModel):
    row_number: int
    errors: list[TeacherImportIssue]


class TeacherImportEmailResult(BaseModel):
    teacher_id: UUID
    email: str
    success: bool
    error: str | None = None
    temp_password: str | None = None


class TeacherImportCommitResponse(BaseModel):
    status: str
    created: int
    failed: int
    emails_sent: int
    emails_failed: int
    rows: list[TeacherImportCommitRow]
    failures: list[TeacherImportFailure]
    email_results: list[TeacherImportEmailResult]


class ParentLinkImportIssue(BaseModel):
    code: str
    field: str | None = None
    message: str


class ParentLinkImportPreviewRow(BaseModel):
    row_number: int
    student_number: str
    student_id: UUID | None = None
    student_name: str | None = None
    parent_name: str
    parent_email: str
    parent_phone: str
    relationship: str
    parent_action: str
    link_action: str
    is_valid: bool
    errors: list[ParentLinkImportIssue]
    warnings: list[ParentLinkImportIssue]


class ParentLinkImportPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ParentLinkImportPreviewRow]


class ParentLinkImportCommitRow(BaseModel):
    row_number: int
    status: str
    student_id: UUID | None = None
    parent_id: UUID | None = None
    link_id: UUID | None = None
    parent_action: str | None = None


class ParentLinkImportFailure(BaseModel):
    row_number: int
    errors: list[ParentLinkImportIssue]


class ParentLinkImportEmailResult(BaseModel):
    parent_id: UUID
    email: str
    success: bool
    error: str | None = None
    temp_password: str | None = None


class ParentLinkImportCommitResponse(BaseModel):
    status: str
    linked: int
    reactivated: int
    skipped_existing: int
    failed: int
    parents_reused: int
    parents_created: int
    emails_sent: int
    emails_failed: int
    rows: list[ParentLinkImportCommitRow]
    failures: list[ParentLinkImportFailure]
    email_results: list[ParentLinkImportEmailResult]


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


class ParentGradeResponse(BaseModel):
    course_id: UUID
    course_name: str
    grade_item_id: UUID
    item_title: str
    item_type: str | None = None
    category: str | None = None
    score: float
    max_score: float
    term: str
    school_year: str
    created_at: datetime
    updated_at: datetime


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
    teacher_id: UUID | None = None
    term: str
    school_year: str
    language_group: LanguageGroup | None = None
    class_id: UUID | None = None
    class_name: str | None = None
    class_school_level: str | None = None
    subject_id: UUID | None = None
    coefficient: int = 1
    grading_system: GradingSystem | None = None
    student_count: int = 0
    grade_item_count: int = 0
    filled_score_count: int = 0
    possible_score_count: int = 0


class CourseCreate(BaseModel):
    # Optional when subject_id is provided (the route derives name from the
    # subject); still required for free-text courses — enforced in the route.
    name: str | None = None
    code: str
    teacher_id: UUID | None = None
    term: TrimesterTerm
    school_year: str
    language_group: LanguageGroup | None = None
    class_id: UUID | None = None
    subject_id: UUID | None = None
    # ge=1: a zero coefficient silently drops the course from the class
    # average and a negative one corrupts it.
    coefficient: int = Field(default=1, ge=1)
    # Optional preserves the existing setup-based default for older clients.
    grading_system: GradingSystem | None = None


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
    grading_system: GradingSystem | None = None
    confirm_grading_system_change: bool = False


class CourseBulkPreviewRequest(BaseModel):
    school_year: str
    term: TrimesterTerm
    class_ids: list[UUID] = Field(min_length=1)


class CourseBulkPreviewRow(BaseModel):
    class_id: UUID
    class_name: str
    subject_id: UUID
    subject_name: str
    language_group: LanguageGroup
    sort_order: int
    code: str
    coefficient: int = 1
    grading_system: GradingSystem
    teacher_id: UUID | None = None
    already_exists: bool = False
    existing_course_id: UUID | None = None
    code_conflict: bool = False


class CourseBulkPreviewResponse(BaseModel):
    school_year: str
    term: TrimesterTerm
    rows: list[CourseBulkPreviewRow]
    applicable_count: int
    missing_count: int
    existing_count: int


class CourseBulkCreateItem(BaseModel):
    class_id: UUID
    subject_id: UUID
    code: str
    teacher_id: UUID | None = None
    coefficient: int = Field(default=1, ge=1)
    grading_system: GradingSystem


class CourseBulkCreateRequest(BaseModel):
    school_year: str
    term: TrimesterTerm
    items: list[CourseBulkCreateItem] = Field(min_length=1)


class CourseBulkValidationFailure(BaseModel):
    class_id: UUID | None = None
    subject_id: UUID | None = None
    code: str
    message: str


class CourseBulkCreateResponse(BaseModel):
    status: str
    created_count: int
    skipped_existing_count: int
    created_course_ids: list[UUID]
    validation_failures: list[CourseBulkValidationFailure] = Field(default_factory=list)


class CourseCloneYearRequest(BaseModel):
    source_year: str
    target_year: str


class CourseCloneYearResponse(BaseModel):
    status: str
    created_count: int
    skipped_count: int = 0
    nothing_to_do: bool = False
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


class GradeBatchEntry(BaseModel):
    student_id: UUID
    grade_item_id: UUID
    # null means "clear this score" and soft-deletes the active Grade row.
    score: float | None = None


class GradeBatchSaveRequest(BaseModel):
    entries: list[GradeBatchEntry]


class GradeResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str | None = None
    student_number: str | None = None
    academic_status: str | None = None
    historical_class_name: str | None = None
    grade_item_id: UUID
    course_id: UUID
    score: float
    submitted_by_teacher_id: UUID


class GradeBatchSaveResponse(BaseModel):
    status: str
    saved_count: int
    deleted_count: int
    skipped_count: int
    grades: list[GradeResponse]


class NotifyGradesPayload(BaseModel):
    student_ids: list[UUID]
    term: TrimesterTerm | None = None


class NotificationChannelCounts(BaseModel):
    email: int = 0
    sms: int = 0


class GradeNotificationResponse(BaseModel):
    recipients: int
    delivered: NotificationChannelCounts
    failed: NotificationChannelCounts
    skipped: NotificationChannelCounts


class CourseResultResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str | None = None
    student_number: str | None = None
    academic_status: str | None = None
    historical_class_name: str | None = None
    historical_school_year: str | None = None
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
    invalidated_count: int = 0
    skipped_students: list[SkippedCourseResultStudent]
    results: list[CourseResultResponse]


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None = None
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
    generate_partial: bool = False


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


class BulletinStudentResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    full_name: str
    student_number: str
    educmaster_number: str | None = None
    class_name: str | None = None


class BulletinClassResponse(BaseModel):
    name_fr: str
    name_en: str | None = None


class BulletinCourseResponse(BaseModel):
    course_id: UUID
    course_name: str
    course_code: str
    average: float
    letter_grade: str
    appreciation: str
    language_group: str | None = None
    moy_int: float | None = None
    mcc: float | None = None
    devoir_score: float | None = None
    composition_score: float | None = None


class BulletinCourseGroupsResponse(BaseModel):
    french_courses: list[BulletinCourseResponse]
    english_courses: list[BulletinCourseResponse]
    untagged_courses: list[BulletinCourseResponse]


class BulletinTrackAverageResponse(BaseModel):
    student: float | None = None
    class_highest: float | None = None
    class_lowest: float | None = None


class BulletinAnnualAveragesResponse(BaseModel):
    french: float | None = None
    english: float | None = None
    bilingual: float | None = None
    complete_terms: list[str]
    missing_terms: list[str]
    complete_term_count: int
    total_term_count: int
    is_partial: bool


class BulletinItemResponse(BaseModel):
    key: str
    en_label: str
    fr_label: str
    letter_grade: str | None = None


class BulletinDisplayResponse(BaseModel):
    student: BulletinStudentResponse
    term_number: int | None = None
    is_final_trimester: bool
    term_ordinal_en: str | None = None
    term_ordinal_fr: str | None = None
    term_dates_en: str | None = None
    term_dates_fr: str | None = None
    school_class: BulletinClassResponse | None = None
    class_effectif: int | None = None
    courses_by_language: BulletinCourseGroupsResponse
    averages_grid: dict[int, dict[str, BulletinTrackAverageResponse]]
    annual_averages: BulletinAnnualAveragesResponse
    conduct_items: list[BulletinItemResponse]
    work_habit_items: list[BulletinItemResponse]
    teacher_comment_fr: str | None = None
    teacher_comment_en: str | None = None
    principal_comment_fr: str | None = None
    principal_comment_en: str | None = None
    grading_key: str


class ReportItemUpdate(BaseModel):
    item_key: str
    letter_grade: LetterGrade | None = None


class ReportCardResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str | None = None
    student_number: str | None = None
    academic_status: str | None = None
    student_class_name: str | None = None
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
    created_at: datetime
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


class ReportCardDetailResponse(ReportCardResponse):
    bulletin: BulletinDisplayResponse


class AdminReportCardDetailResponse(AdminReportCardResponse):
    bulletin: BulletinDisplayResponse


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
    student_class_id: UUID | None = None
    student_class_name: str | None = None
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


class ReportApproveRequest(BaseModel):
    approve_stale: bool = False


class ReportSendRequest(BaseModel):
    send_stale: bool = False


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
    generate_partial: bool = False
    approve_stale: bool = False
    send_stale: bool = False


class PartialReportStudent(BaseModel):
    student_id: UUID
    student_name: str
    student_number: str
    expected_results_count: int
    results_count: int
    missing_course_names: list[str]


class StaleReportStudent(BaseModel):
    student_id: UUID
    student_name: str
    student_number: str
    report_id: UUID
    code: str
    reason: str


class ClassReportStatusRow(BaseModel):
    student_id: UUID
    student_name: str
    student_number: str
    # CourseResults calculated for this student in (term, school_year) —
    # 0 means batch-generate would skip them with no_results.
    results_count: int
    # Active enrolled courses with at least one active grade item for this
    # term/year. Courses with no grade items are setup-only and do not block.
    expected_results_count: int = 0
    missing_results_count: int = 0
    missing_course_names: list[str] = []
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
    skipped_partial_count: int = 0
    partial_students: list[PartialReportStudent] = []
    report_ids: list[UUID]


class ReportBulkGenerateRequest(BaseModel):
    school_year: str
    term: TrimesterTerm
    generate_partial: bool = False


class ReportGenerationClassResult(BaseModel):
    class_id: UUID
    class_name: str
    generated_count: int
    skipped_existing_count: int
    skipped_no_results_count: int
    skipped_partial_count: int = 0
    failed: bool = False
    error: str | None = None
    report_ids: list[UUID] = []


class ReportGenerationJobResponse(BaseModel):
    job_id: UUID
    school_year: str
    term: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class ClassReportBatchApproveResponse(BaseModel):
    status: str
    approved_count: int
    skipped_count: int
    skipped_stale_count: int = 0
    stale_reports: list[StaleReportStudent] = []


class ClassReportBatchSendResponse(BaseModel):
    status: str
    sent_count: int
    failed_count: int
    no_recipient_count: int
    skipped_stale_count: int = 0
    stale_reports: list[StaleReportStudent] = []


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
