import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.config import settings
from app.core.exceptions import SentimentAppException, RateLimitExceededException
from app.db.database import SessionLocal
from app.db.repository import SentimentRepository
from app.api.routes import router as api_router
from app.utils.logging import logger
from alembic.config import Config
from alembic import command
from fastapi.openapi.utils import get_openapi
from app.api.schemas import JobCompletedEvent, JobFailedEvent, JobProgressEvent


def run_migrations():
    """Run Alembic migrations programmatically to bring the database schema to head."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ini_path = os.path.join(base_dir, "alembic.ini")
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))

    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite") and ":memory:" not in db_url:
        db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.isabs(db_path):
            db_path = os.path.normpath(os.path.join(base_dir, db_path))
            db_url = f"sqlite:///{db_path}"
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run Alembic migrations programmatically (failures raise and are not swallowed)
    logger.info("Running database migrations via Alembic...")
    run_migrations()
    logger.info("Database schema successfully upgraded to head.")

    # Startup: recover any leftover jobs from unexpected crash/restart
    logger.info("Initializing Market Sentiment Analysis application...")
    db = SessionLocal()
    try:
        recovered = SentimentRepository.recover_orphaned_jobs(db)
        if recovered > 0:
            logger.warning(f"Recovered and marked {recovered} orphaned job(s) as FAILED on startup.")
    finally:
        db.close()

    # Startup: Initialize shared HTTP client and PipelineDeps
    import httpx
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0),
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        follow_redirects=True,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    )
    from app.core.models import PipelineDeps
    pipeline_deps = PipelineDeps(
        http_client=http_client,
        session_factory=SessionLocal,
    )
    app.state.http_client = http_client
    app.state.pipeline_deps = pipeline_deps

    try:
        yield
    finally:
        logger.info("Shutting down Market Sentiment Analysis application.")
        await http_client.aclose()
        from app.services.llm_service import LLMService
        await LLMService.close_client()


app = FastAPI(
    title="Market Sentiment Analysis API",
    description="Empirical research and directional market-sentiment classification for US Equities, ETFs, Forex pairs, Cryptocurrencies, and Commodities.",
    version="1.0.0",
    lifespan=lifespan,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = openapi_schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    for model in (JobProgressEvent, JobCompletedEvent, JobFailedEvent):
        model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = model_schema.pop("$defs", {})
        for def_name, def_schema in defs.items():
            if def_name not in schemas:
                schemas[def_name] = def_schema
        schemas[model.__name__] = model_schema
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified API exception handlers returning {error, message, details}
@app.exception_handler(SentimentAppException)
async def domain_exception_handler(request: Request, exc: SentimentAppException):
    headers = {}
    if isinstance(exc, RateLimitExceededException) or "retry_after_seconds" in exc.details:
        retry_after = exc.details.get("retry_after_seconds", getattr(exc, "retry_after_seconds", 60))
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers if headers else None,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "RequestValidationError",
            "message": "Validation error in request parameters or body.",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None) or None,
        content={
            "error": "HTTPException",
            "message": str(exc.detail),
            "details": {},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())
    logger.exception(f"Unhandled server error [error_id={error_id}]: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An internal server error occurred.",
            "details": {"error_id": error_id},
        },
    )

# Include API routes
app.include_router(api_router)

# Mount static frontend if directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
