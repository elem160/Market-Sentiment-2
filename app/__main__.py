import uvicorn

from app.config import settings


def main() -> None:
    forwarded_ips = (
        ",".join(settings.TRUSTED_PROXY_IPS)
        if settings.TRUSTED_PROXY_IPS
        else ("*" if settings.TRUST_PROXY_HEADERS else None)
    )
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        workers=1,
        proxy_headers=settings.TRUST_PROXY_HEADERS,
        forwarded_allow_ips=forwarded_ips,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
