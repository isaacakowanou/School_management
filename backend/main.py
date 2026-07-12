"""Assemble the FastAPI application and its cross-cutting HTTP boundaries.

Router prefixes are centralized here so route modules describe paths relative
to one versioned ``/api/v1`` surface. SlowAPI's shared limiter is installed on
the application, and every FastAPI ``HTTPException`` keeps its existing body
while gaining ``X-Error-Code`` for frontend localization. That header boundary
must not replace structured ``detail.code`` or expose raw backend English as UI
copy; the frontend resolves both to localized messages.
"""

import config  # noqa: F401
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import HTTPException

from limiter import limiter
from error_codes import error_code_for_exception
from routes.audit_logs import router as audit_logs_router
from routes.admin_stats import router as admin_stats_router
from routes.ai import router as ai_router
from routes.auth import router as auth_router
from routes.classes import router as classes_router
from routes.course_results import router as course_results_router
from routes.courses import router as courses_router
from routes.danger_zone import router as danger_zone_router
from routes.enrollments import router as enrollments_router
from routes.grade_items import router as grade_items_router
from routes.grades import router as grades_router
from routes.parents import router as parents_router
from routes.reports import router as reports_router
from routes.students import router as students_router
from routes.subjects import router as subjects_router
from routes.teachers import router as teachers_router
from routes.trash import router as trash_router
from routes.users import router as users_router


app = FastAPI(
    title="School AI Grade & Report-Card Management System",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(HTTPException)
async def localized_http_exception_handler(request: Request, exc: HTTPException):
    response = await http_exception_handler(request, exc)
    response.headers["X-Error-Code"] = error_code_for_exception(exc)
    return response

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(audit_logs_router, prefix="/api/v1")
app.include_router(admin_stats_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1/ai")
app.include_router(classes_router, prefix="/api/v1/classes")
app.include_router(course_results_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1/courses")
app.include_router(danger_zone_router, prefix="/api/v1")
app.include_router(enrollments_router, prefix="/api/v1")
app.include_router(grade_items_router, prefix="/api/v1")
app.include_router(grades_router, prefix="/api/v1")
app.include_router(parents_router, prefix="/api/v1/parents")
app.include_router(reports_router, prefix="/api/v1/reports")
app.include_router(students_router, prefix="/api/v1/students")
app.include_router(subjects_router, prefix="/api/v1/subjects")
app.include_router(teachers_router, prefix="/api/v1/teachers")
app.include_router(trash_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1/users")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
