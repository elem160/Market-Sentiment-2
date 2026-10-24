import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.database import SessionLocal, engine
from app.db.models import AnalysisJobDB, AnalysisRunDB

logger = logging.getLogger(__name__)


def delete_expired_jobs(db: Session, now: datetime | None = None) -> int:
    """
    Deletes analysis jobs where expires_at < now.
    Returns count of deleted jobs.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    num_deleted = (
        db.query(AnalysisJobDB)
        .filter(AnalysisJobDB.expires_at < now)
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info(f"Purged {num_deleted} expired analysis jobs (expires_at < {now.isoformat()}).")
    return num_deleted


def delete_old_analysis_runs(
    db: Session,
    retention_days: int = settings.RUN_RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """
    Deletes analysis runs older than retention_days (created_at < cutoff).
    Cascades deletion to ArticleEvidenceDB and ObservedFactDB.
    Returns count of deleted runs.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cutoff = now - timedelta(days=retention_days)
    old_runs = (
        db.query(AnalysisRunDB)
        .filter(AnalysisRunDB.created_at < cutoff)
        .all()
    )
    count = len(old_runs)
    for run in old_runs:
        db.delete(run)
    db.commit()
    logger.info(
        f"Purged {count} old analysis runs (retention_days={retention_days}, cutoff={cutoff.isoformat()})."
    )
    return count


def run_maintenance(
    session_factory: sessionmaker[Session] | None = None,
    retention_days: int = settings.RUN_RETENTION_DAYS,
    vacuum: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Executes database lifecycle maintenance:
    - Purges expired analysis jobs
    - Purges analysis runs older than retention_days with cascaded evidence & facts
    - Optionally vacuums SQLite database
    """
    factory = session_factory or SessionLocal
    db: Session = factory()
    try:
        expired_jobs = delete_expired_jobs(db, now=now)
        old_runs = delete_old_analysis_runs(db, retention_days=retention_days, now=now)
    finally:
        db.close()

    vacuum_performed = False
    if vacuum:
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("VACUUM;"))
            vacuum_performed = True
            logger.info("Database VACUUM completed successfully.")
        except Exception as e:
            logger.warning(f"Database VACUUM encountered an error: {e}")

    result = {
        "expired_jobs_deleted": expired_jobs,
        "old_runs_deleted": old_runs,
        "vacuumed": vacuum_performed,
    }
    return result
