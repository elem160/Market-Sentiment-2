from datetime import datetime, timezone
from sqlalchemy import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """
    SQLAlchemy TypeDecorator for timezone-aware UTC datetimes.
    - On bind (write): converts aware datetimes to UTC; rejects naive datetimes.
    - On result (read): attaches timezone.utc so returned values are always timezone-aware.
    Storage format remains standard DateTime so SQLite storage and alembic schema checks stay clean.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected datetime, got {type(value).__name__}: {value}")
        if value.tzinfo is None:
            raise ValueError(f"Naive datetime rejected by UTCDateTime: {value!r}. All datetimes must be timezone-aware (e.g. timezone.utc).")
        # Store as naive UTC in SQLite (standard convention for SQLite DateTime)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
