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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    description="Empirical research and directional market-sentiment classification for US Equities and ETFs.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
