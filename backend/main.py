from fastapi import FastAPI

from routes.auth import router as auth_router
from routes.courses import router as courses_router
from routes.parents import router as parents_router
from routes.students import router as students_router
from routes.teachers import router as teachers_router
from routes.users import router as users_router


app = FastAPI(
    title="School AI Grade & Report-Card Management System",
    version="0.1.0",
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(courses_router, prefix="/api/v1/courses")
app.include_router(parents_router, prefix="/api/v1/parents")
app.include_router(students_router, prefix="/api/v1/students")
app.include_router(teachers_router, prefix="/api/v1/teachers")
app.include_router(users_router, prefix="/api/v1/users")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
