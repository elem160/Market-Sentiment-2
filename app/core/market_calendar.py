"""
NYSE Market Calendar module.
Provides explicit dated tables for NYSE holidays, special closures, and early closes
for 2025–2027 (verified against nyse.com), with rule-based algorithmic fallback for other years.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")

# Explicit NYSE Holiday dates (verified against nyse.com)
NYSE_HOLIDAYS_TABLE: dict[int, set[date]] = {
    2025: {
        date(2025, 1, 1),    # New Year's Day
        date(2025, 1, 9),    # National Day of Mourning for President Jimmy Carter
        date(2025, 1, 20),   # Martin Luther King Jr. Day
        date(2025, 2, 17),   # Washington's Birthday (Presidents' Day)
        date(2025, 4, 18),   # Good Friday
        date(2025, 5, 26),   # Memorial Day
        date(2025, 6, 19),   # Juneteenth National Independence Day
        date(2025, 7, 4),    # Independence Day
        date(2025, 9, 1),    # Labor Day
        date(2025, 11, 27),  # Thanksgiving Day
        date(2025, 12, 25),  # Christmas Day
    },
    2026: {
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # Martin Luther King Jr. Day
        date(2026, 2, 16),   # Washington's Birthday (Presidents' Day)
        date(2026, 4, 3),    # Good Friday
        date(2026, 5, 25),   # Memorial Day
        date(2026, 6, 19),   # Juneteenth National Independence Day
        date(2026, 7, 3),    # Independence Day observed (July 4 is Saturday)
        date(2026, 9, 7),    # Labor Day
        date(2026, 11, 26),  # Thanksgiving Day
        date(2026, 12, 25),  # Christmas Day
    },
    2027: {
        date(2027, 1, 1),    # New Year's Day
        date(2027, 1, 18),   # Martin Luther King Jr. Day
        date(2027, 2, 15),   # Washington's Birthday (Presidents' Day)
        date(2027, 3, 26),   # Good Friday
        date(2027, 5, 31),   # Memorial Day
        date(2027, 6, 18),   # Juneteenth observed (June 19 is Saturday)
        date(2027, 7, 5),    # Independence Day observed (July 4 is Sunday)
        date(2027, 9, 6),    # Labor Day
        date(2027, 11, 25),  # Thanksgiving Day
        date(2027, 12, 24),  # Christmas Day observed (Dec 25 is Saturday)
    },
}

# Explicit NYSE Early Close dates (13:00 ET close, verified against nyse.com)
NYSE_EARLY_CLOSES_TABLE: dict[int, set[date]] = {
    2025: {
        date(2025, 7, 3),    # Day before Independence Day
        date(2025, 11, 28),  # Day after Thanksgiving (Black Friday)
        date(2025, 12, 24),  # Christmas Eve
    },
    2026: {
        date(2026, 11, 27),  # Day after Thanksgiving (Black Friday)
        date(2026, 12, 24),  # Christmas Eve
    },
    2027: {
        date(2027, 7, 2),    # Friday before Independence Day weekend
        date(2027, 11, 26),  # Day after Thanksgiving (Black Friday)
    },
}


def _calculate_easter(year: int) -> date:
    """Anonymous Gregorian algorithm to compute Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a month (weekday: 0=Monday..6=Sunday, n: 1-indexed)."""
    first_day = date(year, month, 1)
    first_weekday = first_day.weekday()
    day_offset = (weekday - first_weekday) % 7
    first_target = first_day + timedelta(days=day_offset)
    return first_target + timedelta(weeks=n - 1)


def _get_last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    day_offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=day_offset)


def _get_observed_holiday(target_date: date) -> date:
    """If holiday falls on Saturday -> observed Friday; if Sunday -> observed Monday."""
    if target_date.weekday() == 5:  # Saturday
        return target_date - timedelta(days=1)
    elif target_date.weekday() == 6:  # Sunday
        return target_date + timedelta(days=1)
    return target_date


def _fallback_nyse_holidays(year: int) -> set[date]:
    """Rule-based NYSE holidays for years outside the 2025–2027 explicit table."""
    holidays = {
        _get_observed_holiday(date(year, 1, 1)),                  # New Year's Day
        _get_nth_weekday_of_month(year, 1, 0, 3),                 # Martin Luther King Jr. Day (3rd Mon in Jan)
        _get_nth_weekday_of_month(year, 2, 0, 3),                 # Washington's Birthday (3rd Mon in Feb)
        _calculate_easter(year) - timedelta(days=2),              # Good Friday
        _get_last_weekday_of_month(year, 5, 0),                   # Memorial Day (Last Mon in May)
        _get_observed_holiday(date(year, 7, 4)),                  # Independence Day
        _get_nth_weekday_of_month(year, 9, 0, 1),                 # Labor Day (1st Mon in Sep)
        _get_nth_weekday_of_month(year, 11, 3, 4),                # Thanksgiving (4th Thu in Nov)
        _get_observed_holiday(date(year, 12, 25)),                # Christmas Day
    }
    # Juneteenth only official federal holiday from 2022 onwards
    if year >= 2022:
        holidays.add(_get_observed_holiday(date(year, 6, 19)))
    return holidays


def _fallback_nyse_early_closes(year: int) -> set[date]:
    """Rule-based early closes (13:00 ET) for years outside 2025–2027."""
    early_closes: set[date] = set()

    # Day after Thanksgiving (Black Friday)
    thanksgiving = _get_nth_weekday_of_month(year, 11, 3, 4)
    early_closes.add(thanksgiving + timedelta(days=1))

    # Christmas Eve (Dec 24) if on a weekday and not observed Christmas Day
    xmas_eve = date(year, 12, 24)
    if xmas_eve.weekday() < 5 and date(year, 12, 25).weekday() != 5:
        early_closes.add(xmas_eve)

    # Day before Independence Day
    july4 = date(year, 7, 4)
    if july4.weekday() in (1, 2, 3, 4):  # Tue-Fri -> July 3 is early close
        early_closes.add(date(year, 7, 3))
    elif july4.weekday() == 6:  # Sunday (observed Mon July 5) -> Friday July 2 is early close
        early_closes.add(date(year, 7, 2))

    return early_closes


def is_nyse_holiday(d: date) -> bool:
    """Check if date is an official NYSE market holiday or special closure."""
    if d.year in NYSE_HOLIDAYS_TABLE:
        return d in NYSE_HOLIDAYS_TABLE[d.year]
    return d in _fallback_nyse_holidays(d.year)


def is_early_close(d: date) -> bool:
    """Check if date is a scheduled NYSE early close (13:00 ET)."""
    if d.year in NYSE_EARLY_CLOSES_TABLE:
        return d in NYSE_EARLY_CLOSES_TABLE[d.year]
    return d in _fallback_nyse_early_closes(d.year)


def is_trading_day(d: date) -> bool:
    """Check if date is a regular active trading day (Mon-Fri and not a holiday)."""
    return d.weekday() < 5 and not is_nyse_holiday(d)


def get_market_close_time(d: date) -> time:
    """Return closing time in America/New_York (13:00 for early close, 16:00 otherwise)."""
    if is_early_close(d):
        return time(13, 0, 0)
    return time(16, 0, 0)


def get_previous_trading_day(ref_date: date) -> date:
    """Find the most recent active trading day strictly prior to ref_date."""
    cur = ref_date - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur
