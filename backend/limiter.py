from fastapi import Request
from slowapi import Limiter


def _get_client_ip(request: Request) -> str:
    """Read the real client IP, trusting X-Forwarded-For from Render's load balancer."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_client_ip)
