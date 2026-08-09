"""GPS week/time helpers for JXL observation timestamps."""

from __future__ import annotations

import bisect
import datetime
from typing import Optional

import arrow

__all__ = ["gps_time_to_utc"]

_GPS_EPOCH = datetime.datetime(
    1980, 1, 6, 0, 0, 0, tzinfo=datetime.timezone.utc
)
_SECONDS_PER_WEEK = 7 * 24 * 60 * 60

#: UTC instants when leap seconds were inserted (same table as SurvCE GT).
_LEAP_SECOND_BOUNDARIES = (
    datetime.datetime(1981, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1982, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1983, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1985, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1988, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1990, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1991, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1992, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1993, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1994, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1996, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1997, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(1999, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2006, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2009, 1, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2012, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2015, 7, 1, tzinfo=datetime.timezone.utc),
    datetime.datetime(2017, 1, 1, tzinfo=datetime.timezone.utc),
)


def _leap_seconds(moment: datetime.datetime) -> int:
    """Return leap-second count on or before ``moment``."""
    return bisect.bisect(_LEAP_SECOND_BOUNDARIES, moment)


def gps_time_to_utc(gps_week: int, seconds: float) -> datetime.datetime:
    """Convert GPS week and seconds-of-week to aware UTC.

    Args:
        gps_week: GPS week number from the JXL ``GPSWeek`` element.
        seconds: Seconds since the start of ``gps_week`` (may be
            fractional).

    Returns:
        The corresponding aware UTC :class:`datetime.datetime`.
    """
    whole_seconds, fractional = divmod(seconds, 1.0)
    milliseconds = int(round(fractional * 1000.0))
    naive = _GPS_EPOCH + datetime.timedelta(
        seconds=gps_week * _SECONDS_PER_WEEK + int(whole_seconds),
        milliseconds=milliseconds,
    )
    corrected = naive - datetime.timedelta(seconds=_leap_seconds(naive))
    return arrow.get(corrected, tzinfo="UTC").datetime


def parse_gps_seconds(text: Optional[str]) -> Optional[float]:
    """Parse JXL ``Seconds`` text into a float, or ``None`` when invalid."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None
