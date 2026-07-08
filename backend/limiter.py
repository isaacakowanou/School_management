from fastapi import Request
from slowapi import Limiter


def _get_client_ip(request: Request) -> str:
    """Read the real client IP, trusting X-Forwarded-For from Render's load balancer.

    Render's proxy APPENDS the true client IP to whatever X-Forwarded-For the
    client sent, so only the LAST entry is trustworthy. Taking the first entry
    would let an attacker rotate spoofed header values to bypass the login
    rate limit.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_client_ip)
