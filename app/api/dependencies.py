from fastapi import Request
from app.db.database import get_db

def get_client_ip(request: Request) -> str:
    """Extract client IP handling x-forwarded-for if present."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
