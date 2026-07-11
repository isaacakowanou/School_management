from fastapi import HTTPException


ERROR_CODE_BY_MESSAGE = {
    "Invalid credentials": "invalid_credentials",
    "Insufficient permissions": "insufficient_permissions",
    "Student not found": "student_not_found",
    "Parent not found": "parent_not_found",
    "Teacher not found": "teacher_not_found",
    "Course not found": "course_not_found",
    "Grade item not found": "grade_item_not_found",
    "Grade not found": "grade_not_found",
    "Enrollment not found": "enrollment_not_found",
    "Report card not found": "report_not_found",
    "Email already exists": "email_exists",
    "Student number already exists": "student_number_exists",
    "Employee number already exists": "employee_number_exists",
    "Course code already exists": "course_code_exists",
    "Student is already enrolled": "student_already_enrolled",
    "Student is not enrolled in this course": "student_not_enrolled",
    "Parent is already linked to student": "parent_already_linked",
    "score must be greater than or equal to 0": "score_negative",
    "score cannot exceed max_score": "score_above_max",
    "Grade already exists": "grade_exists",
    "term must be a canonical trimester": "term_not_canonical",
    "Confirmation does not match": "confirmation_mismatch",
    "Danger Zone is disabled in production": "cleanup_disabled",
    "Trash entry not found": "trash_entry_not_found",
    "Only draft reports can be reviewed": "report_not_draft",
    "Only approved or sent reports can be sent": "report_not_sendable",
    "Invalid identifier or OTP": "invalid_otp",
    "Invalid or expired reset link": "invalid_reset_link",
    "No approved or sent reports for this class and term": "no_class_reports",
}


def error_code_for_exception(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict) and isinstance(exc.detail.get("code"), str):
        return exc.detail["code"]
    if isinstance(exc.detail, str):
        if exc.detail in ERROR_CODE_BY_MESSAGE:
            return ERROR_CODE_BY_MESSAGE[exc.detail]
        if exc.detail.endswith(" cannot be empty"):
            return "required_field_empty"
        if exc.detail.startswith("Course has no grade items"):
            return "course_has_no_grade_items"
        if "must have exactly one Devoir" in exc.detail:
            return "missing_devoir"
        if "must have exactly one Composition" in exc.detail:
            return "missing_composition"
        if "has no Interro grade items" in exc.detail:
            return "missing_interro"
    return "request_failed"
