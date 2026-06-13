"""
Resolve reporting windows.

All windows are half-open ``[start, end)`` where ``start`` is the start of the
first day and ``end`` is the start of the day *after* the last included day.
This makes datetime filters (``created_at < end``) and date filters
(``expense_date < end.date()``) consistent and off-by-one-free.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone


def _day_start(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.min))


def named_bounds(name: str, today: date | None = None) -> tuple[datetime, datetime]:
    """Half-open [start, end) datetime bounds for a named period."""
    today = today or timezone.localdate()
    name = (name or "month").lower()

    if name == "today":
        start, last = today, today
    elif name == "yesterday":
        y = today - timedelta(days=1)
        start, last = y, y
    elif name == "week":
        start, last = today - timedelta(days=today.weekday()), today  # Monday → today
    elif name == "year":
        start, last = today.replace(month=1, day=1), today
    else:  # month (default)
        start, last = today.replace(day=1), today

    return _day_start(start), _day_start(last + timedelta(days=1))


def resolve_period(params) -> tuple[datetime, datetime, str]:
    """
    Accepts ?period=today|yesterday|week|month|year  OR  ?start=&end= (YYYY-MM-DD).
    Returns half-open [start, end) bounds and a human label.
    """
    start_q = params.get("start")
    end_q = params.get("end")
    if start_q and end_q:
        start = date.fromisoformat(start_q)
        end = date.fromisoformat(end_q)
        return _day_start(start), _day_start(end + timedelta(days=1)), f"{start} → {end}"

    period = (params.get("period") or "month").lower()
    start, end = named_bounds(period)
    label = "Yesterday" if period == "yesterday" else period.capitalize()
    return start, end, label
