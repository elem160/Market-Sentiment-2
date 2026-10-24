import ipaddress
from typing import Callable
from fastapi import Depends, Header, Request
from app.config import settings
from app.core.exceptions import UnauthorizedException
from app.utils.rate_limiter import rate_limiter


def is_ip_trusted(ip_str: str, trusted_list: list[str]) -> bool:
    """Check if an IP string matches any trusted IP or CIDR network block."""
    if not ip_str or not trusted_list:
        return False
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    for trusted_entry in trusted_list:
        trusted_entry = trusted_entry.strip()
        if not trusted_entry:
            continue
        try:
            if "/" in trusted_entry:
                network = ipaddress.ip_network(trusted_entry, strict=False)
                if ip in network:
                    return True
            else:
                trusted_ip = ipaddress.ip_address(trusted_entry)
                if ip == trusted_ip:
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request: Request) -> str:
    """
    Extract client IP safely according to RFC 7239 / proxy walking principles:
    - If TRUST_PROXY_HEADERS is False or direct peer is NOT in TRUSTED_PROXY_IPS:
      returns direct peer address.
    - If direct peer IS in TRUSTED_PROXY_IPS:
      walks X-Forwarded-For from RIGHT TO LEFT, skipping trusted proxy hops,
      and returns the first untrusted IP (the genuine client).
    """
    peer_ip = request.client.host if request.client else "127.0.0.1"

    if not settings.TRUST_PROXY_HEADERS:
        return peer_ip

    if not settings.TRUSTED_PROXY_IPS:
        return peer_ip

    # Verify direct connection peer is trusted
    if not is_ip_trusted(peer_ip, settings.TRUSTED_PROXY_IPS):
        return peer_ip

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return peer_ip

    hops = [h.strip() for h in xff.split(",") if h.strip()]
    if not hops:
        return peer_ip

    # Walk right-to-left: the rightmost hop was appended by the peer we trust
    for hop in reversed(hops):
        if is_ip_trusted(hop, settings.TRUSTED_PROXY_IPS):
            continue
        # First untrusted hop from the right is the genuine client
        return hop

    # If all hops were trusted, return the leftmost hop
    return hops[0]


def rate_limit(scope: str) -> Callable:
    """
    FastAPI dependency factory enforcing scoped sliding window rate limits.
    Scopes:
    - 'analyze': settings.RATE_LIMIT_ANALYSIS_PER_MINUTE (default 15/min)
    - 'jobs': settings.RATE_LIMIT_JOBS_PER_MINUTE (default 60/min)
    - 'read': settings.RATE_LIMIT_READ_PER_MINUTE (default 120/min)
    """
    async def dependency(client_ip: str = Depends(get_client_ip)) -> str:
        if scope == "analyze":
            limit = settings.RATE_LIMIT_ANALYSIS_PER_MINUTE
        elif scope == "jobs":
            limit = settings.RATE_LIMIT_JOBS_PER_MINUTE
        elif scope == "read":
            limit = settings.RATE_LIMIT_READ_PER_MINUTE
        else:
            limit = 60

        rate_limiter.check(scope, client_ip, max_requests=limit, window_seconds=60)
        return client_ip

    return dependency


def verify_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """
    Verify optional API key for guarded endpoints.
    If settings.API_KEY is configured (non-empty), request must supply matching X-API-Key header.
    """
    expected = settings.API_KEY
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected.strip():
        raise UnauthorizedException("Invalid or missing API key")


def verify_history_access(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """
    Enforce API key verification on history and analysis inspection endpoints
    if settings.PUBLIC_HISTORY is False and settings.API_KEY is configured.
    """
    if settings.PUBLIC_HISTORY:
        return
    expected = settings.API_KEY
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected.strip():
        raise UnauthorizedException("Invalid or missing API key")

