"""Helpers for request-scoped lighting relevance classification.

This module resolves whether lighting penalties should be treated as relevant
for a route request (daylight/twilight/night). The implementation intentionally
avoids heavyweight dependencies and uses a deterministic solar approximation
from request UTC time and route midpoint coordinates.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Dict, Optional, Tuple


VALID_LIGHTING_CONTEXTS = frozenset({'daylight', 'twilight', 'night'})
_TWILIGHT_BUFFER_HOURS = 0.75  # 45 minutes on each side of sunrise/sunset


def _parse_utc_datetime(value) -> datetime:
    """Parse ISO timestamp input to timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        dt = datetime.fromisoformat(raw)
    else:
        return datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _normalise_context(value: Optional[str]) -> str:
    context = str(value or 'auto').strip().lower()
    if context in VALID_LIGHTING_CONTEXTS:
        return context
    return 'auto'


def _route_midpoint(
    start_point: Tuple[float, float],
    end_point: Optional[Tuple[float, float]] = None,
) -> Tuple[float, float]:
    """Return midpoint latitude/longitude used for solar phase estimation."""
    if not end_point:
        return start_point

    return (
        (float(start_point[0]) + float(end_point[0])) / 2.0,
        (float(start_point[1]) + float(end_point[1])) / 2.0,
    )


def _solar_phase(
    latitude: float,
    longitude: float,
    dt_utc: datetime,
) -> Tuple[str, Dict[str, float]]:
    """Classify daylight/twilight/night using a lightweight solar model."""
    lat = max(-89.0, min(89.0, float(latitude)))
    lon = float(longitude)

    day_of_year = dt_utc.timetuple().tm_yday

    # Approximate solar declination (degrees).
    declination_deg = 23.44 * math.sin(math.radians((360.0 / 365.0) * (day_of_year - 81)))

    lat_rad = math.radians(lat)
    declination_rad = math.radians(declination_deg)

    cos_omega = -math.tan(lat_rad) * math.tan(declination_rad)

    if cos_omega <= -1.0:
        # Polar day.
        return 'daylight', {
            'solar_hour': 12.0,
            'sunrise_solar_hour': 0.0,
            'sunset_solar_hour': 24.0,
        }

    if cos_omega >= 1.0:
        # Polar night.
        return 'night', {
            'solar_hour': 12.0,
            'sunrise_solar_hour': 12.0,
            'sunset_solar_hour': 12.0,
        }

    omega_deg = math.degrees(math.acos(cos_omega))
    daylight_hours = 2.0 * omega_deg / 15.0
    sunrise = 12.0 - (daylight_hours / 2.0)
    sunset = 12.0 + (daylight_hours / 2.0)

    utc_hour = (
        dt_utc.hour
        + (dt_utc.minute / 60.0)
        + (dt_utc.second / 3600.0)
        + (dt_utc.microsecond / 3_600_000_000.0)
    )

    # Approximate local solar hour from longitude (15° per hour).
    solar_hour = (utc_hour + (lon / 15.0)) % 24.0

    if sunrise <= solar_hour < sunset:
        context = 'daylight'
    elif (sunrise - _TWILIGHT_BUFFER_HOURS) <= solar_hour < sunrise:
        context = 'twilight'
    elif sunset <= solar_hour < (sunset + _TWILIGHT_BUFFER_HOURS):
        context = 'twilight'
    else:
        context = 'night'

    return context, {
        'solar_hour': round(solar_hour, 3),
        'sunrise_solar_hour': round(sunrise, 3),
        'sunset_solar_hour': round(sunset, 3),
    }


def resolve_request_lighting_context(
    request_data: Optional[dict],
    start_point: Tuple[float, float],
    end_point: Optional[Tuple[float, float]] = None,
) -> Dict[str, object]:
    """Resolve effective lighting context for a route/loop request."""
    data = request_data or {}

    override = _normalise_context(data.get('lighting_context_override'))
    dt_utc = _parse_utc_datetime(data.get('routing_datetime_utc'))
    lat, lon = _route_midpoint(start_point, end_point)

    if override in VALID_LIGHTING_CONTEXTS:
        return {
            'lighting_context': override,
            'source': 'override',
            'routing_datetime_utc': dt_utc.isoformat(),
            'latitude': round(float(lat), 6),
            'longitude': round(float(lon), 6),
            'solar_meta': None,
        }

    context, solar_meta = _solar_phase(lat, lon, dt_utc)
    return {
        'lighting_context': context,
        'source': 'auto',
        'routing_datetime_utc': dt_utc.isoformat(),
        'latitude': round(float(lat), 6),
        'longitude': round(float(lon), 6),
        'solar_meta': solar_meta,
    }
