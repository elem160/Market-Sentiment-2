import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.core.exceptions import SentimentAppException
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
    yield
    logger.info("Shutting down Market Sentiment Analysis application.")


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
        schemas[model.__name__] = model.model_json_schema()
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

# Global custom domain exception handler
@app.exception_handler(SentimentAppException)
async def domain_exception_handler(request: Request, exc: SentimentAppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )

# Include API routes
app.include_router(api_router)

# Mount static frontend if directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
