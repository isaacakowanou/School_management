from fastapi import FastAPI

from routes.auth import router as auth_router
from routes.users import router as users_router


app = FastAPI(
    title="School AI Grade & Report-Card Management System",
    version="0.1.0",
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(users_router, prefix="/api/v1/users")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
