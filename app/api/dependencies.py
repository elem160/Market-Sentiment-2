from fastapi import Request
from app.config import settings
from app.db.database import get_db

def get_client_ip(request: Request) -> str:
    """Extract client IP, handling x-forwarded-for only if proxy headers are trusted."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
