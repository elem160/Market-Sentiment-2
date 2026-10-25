from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.enums import SessionType
from app.core.market_calendar import (
    get_market_close_time,
    is_early_close,
    is_nyse_holiday,
    is_trading_day,
)
from app.core.session_window import (
    EASTERN_TZ,
    compute_session_bucket,
    compute_session_window,
    validate_cache_bucket_minutes,
)


def test_wednesday_regular_hours():
    """Wed 14:30 ET -> start Tue 16:00 (22.5 h), REGULAR_HOURS, market open."""
    ref_dt = datetime(2026, 10, 14, 14, 30, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.REGULAR_HOURS
    assert window.is_market_open is True
    # Anchor: Tuesday 2026-10-13 16:00 ET
    assert window.window_start_et == datetime(2026, 10, 13, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_end_et == ref_dt
    assert window.window_duration_hours == 22.5
    assert window.market_timezone == "America/New_York"


def test_monday_morning_pre_market():
    """Mon 08:00 ET -> start Fri 16:00 (64 h, weekend included)."""
    # 2026-10-19 is Monday
    ref_dt = datetime(2026, 10, 19, 8, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.PRE_MARKET
    assert window.is_market_open is False
    # Anchor: Friday 2026-10-16 16:00 ET
    assert window.window_start_et == datetime(2026, 10, 16, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 64.0


def test_tuesday_overnight_pre_open():
    """Tue 00:30 ET -> start Mon 16:00 (8.5 h)."""
    # 2026-10-13 is Tuesday
    ref_dt = datetime(2026, 10, 13, 0, 30, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.OVERNIGHT_PRE_OPEN
    assert window.is_market_open is False
    # Anchor: Monday 2026-10-12 16:00 ET
    assert window.window_start_et == datetime(2026, 10, 12, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 8.5


def test_tuesday_after_memorial_day_capped_at_72h():
    """Tue after Memorial Day -> anchor is Friday 16:00 (96.5 h ago), capped at 72 h."""
    # Memorial Day 2026 was Monday May 25. Tuesday is May 26.
    ref_dt = datetime(2026, 5, 26, 16, 30, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.POST_MARKET
    assert window.is_market_open is False
    # Previous trading day was Friday May 22 (16:00 ET = 96.5 h ago) -> capped at run - 72h
    assert window.window_duration_hours == 72.0
    assert window.window_start_et == ref_dt - timedelta(hours=72)
    assert window.window_start_utc == window.run_timestamp_utc - timedelta(hours=72)


def test_monday_after_thanksgiving_early_close():
    """Mon after the day-after-Thanksgiving early close -> start Fri 13:00."""
    # Thanksgiving 2026: Thu Nov 26. Black Friday: Fri Nov 27 (early close 13:00).
    # Monday is Nov 30 at 08:00 ET.
    ref_dt = datetime(2026, 11, 30, 8, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.PRE_MARKET
    assert window.is_market_open is False
    # Anchor: Friday 2026-11-27 13:00 ET (due to early close)
    assert window.window_start_et == datetime(2026, 11, 27, 13, 0, 0, tzinfo=EASTERN_TZ)
    # Fri 13:00 to Mon 08:00 = 67.0 hours
    assert window.window_duration_hours == 67.0


def test_weekend_session():
    """Saturday at 12:00 ET -> WEEKEND_SESSION, window starts at Friday 16:00 ET."""
    ref_dt = datetime(2026, 10, 17, 12, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.WEEKEND_SESSION
    assert window.is_market_open is False
    assert window.window_start_et == datetime(2026, 10, 16, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 20.0


def test_holiday_session():
    """Labor Day 2026 (Mon Sep 7) -> HOLIDAY_OFF_MARKET, window starts at Friday 16:00 ET."""
    ref_dt = datetime(2026, 9, 7, 12, 0, 0, tzinfo=EASTERN_TZ)
    window = compute_session_window(ref_dt)

    assert window.session_type == SessionType.HOLIDAY_OFF_MARKET
    assert window.is_market_open is False
    assert window.window_start_et == datetime(2026, 9, 4, 16, 0, 0, tzinfo=EASTERN_TZ)
    assert window.window_duration_hours == 68.0


def test_early_close_trading_day_session_classification():
    """On Black Friday (early close at 13:00), verify market is open until 13:00 and POST_MARKET starts at 13:00."""
    # 1. 11:00 ET -> Market is open, REGULAR_HOURS
    dt_open = datetime(2026, 11, 27, 11, 0, 0, tzinfo=EASTERN_TZ)
    w_open = compute_session_window(dt_open)
    assert w_open.is_market_open is True
    assert w_open.session_type == SessionType.REGULAR_HOURS

    # 2. 14:00 ET -> Market is closed, POST_MARKET
    dt_post = datetime(2026, 11, 27, 14, 0, 0, tzinfo=EASTERN_TZ)
    w_post = compute_session_window(dt_post)
    assert w_post.is_market_open is False
    assert w_post.session_type == SessionType.POST_MARKET


def test_dst_switch_days():
    """Verify UTC durations across America/New_York DST transitions."""
    # Spring forward: Sunday 2026-03-08 (23-hour day in ET)
    # Mon 2026-03-09 10:00 ET vs Fri 2026-03-06 16:00 ET -> 65h total
    dt_spring = datetime(2026, 3, 9, 10, 0, 0, tzinfo=EASTERN_TZ)
    w_spring = compute_session_window(dt_spring)
    assert w_spring.window_duration_hours == 65.0

    # Fall back: Sunday 2026-11-01 (25-hour day in ET)
    # Mon 2026-11-02 10:00 ET vs Fri 2026-10-30 16:00 ET -> 67h total
    dt_fall = datetime(2026, 11, 2, 10, 0, 0, tzinfo=EASTERN_TZ)
    w_fall = compute_session_window(dt_fall)
    assert w_fall.window_duration_hours == 67.0


def test_cache_bucket_120_minute_flooring():
    """Verify cache bucket floors by minutes since midnight ET, supporting buckets > 60 min."""
    window = compute_session_window(datetime(2026, 10, 14, 14, 30, 0, tzinfo=EASTERN_TZ))

    # At 14:35 ET with 120-minute bucket -> floors to 14:00 (14*60 = 840)
    ref1 = datetime(2026, 10, 14, 14, 35, 0, tzinfo=EASTERN_TZ)
    with patch("app.config.settings.CACHE_INTRADAY_BUCKET_MINUTES", 120):
        b_str1, b_sec1 = compute_session_bucket(window, ref1)
        assert b_str1.endswith("202610141400")
        assert b_sec1 == 7200

    # At 15:59 ET with 120-minute bucket -> still floors to 14:00
    ref2 = datetime(2026, 10, 14, 15, 59, 0, tzinfo=EASTERN_TZ)
    with patch("app.config.settings.CACHE_INTRADAY_BUCKET_MINUTES", 120):
        b_str2, b_sec2 = compute_session_bucket(window, ref2)
        assert b_str2.endswith("202610141400")

    # At 16:05 ET with 120-minute bucket -> floors to 16:00
    ref3 = datetime(2026, 10, 14, 16, 5, 0, tzinfo=EASTERN_TZ)
    with patch("app.config.settings.CACHE_INTRADAY_BUCKET_MINUTES", 120):
        b_str3, b_sec3 = compute_session_bucket(window, ref3)
        assert b_str3.endswith("202610141600")


def test_bucket_validation_rules():
    """Bucket minutes must be between 1 and 1440 and divide 1440 evenly."""
    assert validate_cache_bucket_minutes(15) == 15
    assert validate_cache_bucket_minutes(60) == 60
    assert validate_cache_bucket_minutes(120) == 120
    assert validate_cache_bucket_minutes(1440) == 1440

    with pytest.raises(ValueError, match="between 1 and 1440"):
        validate_cache_bucket_minutes(0)

    with pytest.raises(ValueError, match="between 1 and 1440"):
        validate_cache_bucket_minutes(1441)

    with pytest.raises(ValueError, match="divide 1440 evenly"):
        validate_cache_bucket_minutes(50)  # 1440 / 50 = 28.8


def test_nyse_calendar_specifics():
    """Verify explicit 2025-2027 calendar entries."""
    # Jimmy Carter National Day of Mourning
    assert is_nyse_holiday(date(2025, 1, 9)) is True
    assert is_trading_day(date(2025, 1, 9)) is False

    # Early closes 2025
    assert is_early_close(date(2025, 7, 3)) is True
    assert is_early_close(date(2025, 11, 28)) is True
    assert is_early_close(date(2025, 12, 24)) is True
    assert get_market_close_time(date(2025, 11, 28)) == time(13, 0, 0)
    assert get_market_close_time(date(2025, 11, 26)) == time(16, 0, 0)

    # Juneteenth only from 2022
    assert is_nyse_holiday(date(2020, 6, 19)) is False
    assert is_nyse_holiday(date(2022, 6, 20)) is True  # June 19 was Sunday, observed Monday June 20
    assert is_nyse_holiday(date(2025, 6, 19)) is True
    assert is_nyse_holiday(date(2026, 6, 19)) is True


def test_is_timestamp_in_window():
    """Verify timestamp filtering logic."""
    ref_dt = datetime(2026, 10, 14, 15, 0, 0, tzinfo=timezone.utc)
    window = compute_session_window(ref_dt)

    # In window (1 hour prior to run)
    valid_ts = datetime(2026, 10, 14, 14, 0, 0, tzinfo=timezone.utc)
    assert window.is_timestamp_in_window(valid_ts) is True

    # Future timestamp within clock skew
    future_skew_ts = ref_dt + timedelta(minutes=3)
    assert window.is_timestamp_in_window(future_skew_ts) is True

    # Future timestamp beyond clock skew
    future_ts = ref_dt + timedelta(minutes=15)
    assert window.is_timestamp_in_window(future_ts) is False

    # Old timestamp prior to Tuesday 16:00 ET (which was Tuesday 20:00 UTC)
    old_ts = datetime(2026, 10, 13, 18, 0, 0, tzinfo=timezone.utc)
    assert window.is_timestamp_in_window(old_ts) is False
