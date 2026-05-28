from fastapi import FastAPI

from routes.audit_logs import router as audit_logs_router
from routes.ai import router as ai_router
from routes.auth import router as auth_router
from routes.course_results import router as course_results_router
from routes.courses import router as courses_router
from routes.enrollments import router as enrollments_router
from routes.grade_items import router as grade_items_router
from routes.grades import router as grades_router
from routes.parents import router as parents_router
from routes.reports import router as reports_router
from routes.students import router as students_router
from routes.teachers import router as teachers_router
from routes.users import router as users_router


app = FastAPI(
    title="School AI Grade & Report-Card Management System",
    version="0.1.0",
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(audit_logs_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1/ai")
app.include_router(course_results_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1/courses")
app.include_router(enrollments_router, prefix="/api/v1")
app.include_router(grade_items_router, prefix="/api/v1")
app.include_router(grades_router, prefix="/api/v1")
app.include_router(parents_router, prefix="/api/v1/parents")
app.include_router(reports_router, prefix="/api/v1/reports")
app.include_router(students_router, prefix="/api/v1/students")
app.include_router(teachers_router, prefix="/api/v1/teachers")
app.include_router(users_router, prefix="/api/v1/users")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
