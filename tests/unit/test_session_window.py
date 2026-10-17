from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.core.session_window import compute_session_window, is_nyse_holiday
from app.core.enums import SessionType

EASTERN_TZ = ZoneInfo("America/New_York")


def test_regular_trading_hours_window():
    """Wednesday at 14:30 ET -> REGULAR_HOURS, window starts at midnight ET today."""
    ref_dt = datetime(2026, 10, 14, 14, 30, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.REGULAR_HOURS
    assert window.is_market_open is True
    assert window.window_start_et == datetime(2026, 10, 14, 0, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_end_et == ref_dt
    assert window.window_duration_hours == 14.5
    assert window.market_timezone == "America/New_York"


def test_pre_market_session():
    """Thursday at 07:15 ET -> PRE_MARKET, window starts at midnight ET today."""
    ref_dt = datetime(2026, 10, 15, 7, 15, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.PRE_MARKET
    assert window.is_market_open is False
    assert window.window_start_et == datetime(2026, 10, 15, 0, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 7.25


def test_post_market_session():
    """Tuesday at 18:00 ET -> POST_MARKET, window starts at midnight ET today."""
    ref_dt = datetime(2026, 10, 13, 18, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.POST_MARKET
    assert window.is_market_open is False
    assert window.window_start_et == datetime(2026, 10, 13, 0, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 18.0


def test_weekend_session_anchors_to_friday_close():
    """Saturday at 12:00 ET -> WEEKEND_SESSION, window starts at Friday 16:00 ET."""
    # 2026-10-17 is Saturday
    ref_dt = datetime(2026, 10, 17, 12, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.WEEKEND_SESSION
    assert window.is_market_open is False
    # Prior active day was Friday 2026-10-16 at 16:00 ET
    assert window.window_start_et == datetime(2026, 10, 16, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 20.0  # From Friday 16:00 to Saturday 12:00 = 20 hours


def test_72_hour_lookback_cap():
    """A long holiday or Monday pre-dawn run must not exceed 72 hours max lookback."""
    # Monday at 20:00 ET after a 3-day weekend
    ref_dt = datetime(2026, 10, 19, 20, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)
    assert window.window_duration_hours <= 72.0


def test_is_timestamp_in_window():
    """Verify timestamp filtering logic."""
    ref_dt = datetime(2026, 10, 14, 15, 0, 0, tzinfo=timezone.utc)
    window = compute_session_window(ref_dt)

    # In window (1 hour prior to run)
    valid_ts = datetime(2026, 10, 14, 14, 0, 0, tzinfo=timezone.utc)
    assert window.is_timestamp_in_window(valid_ts) is True

    # Future timestamp (after run)
    future_ts = datetime(2026, 10, 14, 16, 0, 0, tzinfo=timezone.utc)
    assert window.is_timestamp_in_window(future_ts) is False

    # Old timestamp (2 days ago)
    old_ts = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
    assert window.is_timestamp_in_window(old_ts) is False
