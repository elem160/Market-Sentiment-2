from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from app.core.enums import SessionType
from app.core.constants import FUTURE_CLOCK_SKEW_MINUTES
from app.core.market_calendar import (
    EASTERN_TZ,
    is_nyse_holiday,
    is_early_close,
    is_trading_day,
    get_market_close_time,
    get_previous_trading_day,
)


@dataclass(frozen=True)
class SessionWindow:
    market_timezone: str
    session_type: SessionType
    is_market_open: bool
    window_start_utc: datetime
    window_start_et: datetime
    window_end_utc: datetime
    window_end_et: datetime
    window_duration_hours: float
    run_timestamp_utc: datetime
    run_timestamp_et: datetime

    def is_timestamp_in_window(self, dt_utc: datetime | None) -> bool:
        """
        Check if an article's UTC timestamp falls within this session window,
        allowing at most FUTURE_CLOCK_SKEW_MINUTES minutes of future clock skew. Returns False if timestamp is None.
        """
        if dt_utc is None:
            return False
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        skew_allowance = timedelta(minutes=FUTURE_CLOCK_SKEW_MINUTES)
        return self.window_start_utc <= dt_utc <= (self.window_end_utc + skew_allowance)


def get_previous_active_trading_day(ref_date: date) -> date:
    """Backward compatibility alias for get_previous_trading_day."""
    return get_previous_trading_day(ref_date)


def compute_session_window(reference_time: datetime | None = None) -> SessionWindow:
    """
    Computes the exact daily-session window anchored to America/New_York.
    
    Unified Window Rule (Decision D1):
    - window_start = close of the most recent active trading day strictly prior to today's ET date
      (16:00 ET, or 13:00 after an early close), capped at run - 72 h.
    - window_end = Current run time.
    - Session type and is_market_open keep their classification logic while respecting early closes.
    """
    if reference_time is None:
        run_utc = datetime.now(timezone.utc)
    else:
        if reference_time.tzinfo is None:
            run_utc = reference_time.replace(tzinfo=timezone.utc)
        else:
            run_utc = reference_time.astimezone(timezone.utc)

    run_et = run_utc.astimezone(EASTERN_TZ)
    current_date_et = run_et.date()
    current_time_et = run_et.time()

    is_weekend = run_et.weekday() >= 5
    is_holiday = is_nyse_holiday(current_date_et)

    if is_weekend or is_holiday:
        session_type = SessionType.WEEKEND_SESSION if is_weekend else SessionType.HOLIDAY_OFF_MARKET
        is_market_open = False
    else:
        # Active Trading Day
        close_time = get_market_close_time(current_date_et)
        t_pre = time(4, 0, 0)
        t_open = time(9, 30, 0)
        t_close = close_time
        t_post = time(17, 0, 0) if is_early_close(current_date_et) else time(20, 0, 0)

        if t_open <= current_time_et <= t_close:
            session_type = SessionType.REGULAR_HOURS
            is_market_open = True
        elif t_pre <= current_time_et < t_open:
            session_type = SessionType.PRE_MARKET
            is_market_open = False
        elif t_close < current_time_et <= t_post:
            session_type = SessionType.POST_MARKET
            is_market_open = False
        else:
            session_type = SessionType.OVERNIGHT_PRE_OPEN
            is_market_open = False

    # Unified window rule: start at previous active trading day's close, capped at run - 72h
    prev_trading_day = get_previous_trading_day(current_date_et)
    prev_close_time = get_market_close_time(prev_trading_day)
    uncapped_start_et = datetime.combine(prev_trading_day, prev_close_time, tzinfo=EASTERN_TZ)
    earliest_allowed_et = run_et - timedelta(hours=72)
    window_start_et = max(uncapped_start_et, earliest_allowed_et)
    window_end_et = run_et

    window_start_utc = window_start_et.astimezone(timezone.utc)
    window_end_utc = window_end_et.astimezone(timezone.utc)
    duration_hours = round((window_end_utc - window_start_utc).total_seconds() / 3600.0, 2)

    return SessionWindow(
        market_timezone="America/New_York",
        session_type=session_type,
        is_market_open=is_market_open,
        window_start_utc=window_start_utc,
        window_start_et=window_start_et,
        window_end_utc=window_end_utc,
        window_end_et=window_end_et,
        window_duration_hours=duration_hours,
        run_timestamp_utc=run_utc,
        run_timestamp_et=run_et,
    )


def validate_cache_bucket_minutes(minutes: int) -> int:
    """Validates that bucket minutes is between 1 and 1440 and divides 1440 evenly."""
    if minutes < 1 or minutes > 1440:
        raise ValueError(f"Cache bucket minutes must be between 1 and 1440, got {minutes}")
    if 1440 % minutes != 0:
        raise ValueError(f"Cache bucket minutes must divide 1440 evenly, got {minutes}")
    return minutes


def compute_session_bucket(session: SessionWindow, now: datetime | None = None) -> tuple[str, int]:
    """
    Computes deterministic session cache bucket string and bucket duration in seconds.
    - REGULAR_HOURS: floored to CACHE_INTRADAY_BUCKET_MINUTES
    - Non-regular sessions: floored to CACHE_OFF_MARKET_BUCKET_MINUTES
    Flooring is based on minutes since midnight ET, supporting bucket sizes > 60 minutes.
    Returns: (bucket_str, bucket_seconds)
    """
    from app.config import settings
    ref_dt = now or session.run_timestamp_utc
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    ref_et = ref_dt.astimezone(EASTERN_TZ)

    if session.session_type == SessionType.REGULAR_HOURS:
        bucket_mins = validate_cache_bucket_minutes(settings.CACHE_INTRADAY_BUCKET_MINUTES)
    else:
        bucket_mins = validate_cache_bucket_minutes(settings.CACHE_OFF_MARKET_BUCKET_MINUTES)

    # Floor by minutes since midnight ET
    minutes_since_midnight = ref_et.hour * 60 + ref_et.minute
    floored_minutes = (minutes_since_midnight // bucket_mins) * bucket_mins
    floored_hour = floored_minutes // 60
    floored_minute = floored_minutes % 60
    floored_et = ref_et.replace(hour=floored_hour, minute=floored_minute, second=0, microsecond=0)
    bucket_str = f"{session.session_type.value}_{floored_et.strftime('%Y%m%d%H%M')}"
    bucket_seconds = bucket_mins * 60
    return bucket_str, bucket_seconds
