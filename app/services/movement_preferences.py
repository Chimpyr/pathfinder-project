"""
Movement Preference Helpers
==========================

Shared validation and conversion helpers for dynamic movement speed
preferences and travel-profile routing context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from config import Config

KM_PER_MILE = 1.609344
DISTANCE_UNITS = {'km', 'mi'}
TRAVEL_PROFILES = {'walking', 'running_easy', 'running_race'}
PROFILE_TO_ACTIVITY = {
    'walking': 'walking',
    'running_easy': 'running',
    'running_race': 'running',
}
PROFILE_TO_SPEED_FIELD = {
    'walking': 'walking_speed_kmh',
    'running_easy': 'running_easy_speed_kmh',
    'running_race': 'running_race_speed_kmh',
}
SPEED_LIMITS = {
    'walking_speed_kmh': (2.0, 9.0),
    'running_easy_speed_kmh': (4.0, 20.0),
    'running_race_speed_kmh': (6.0, 30.0),
}


def _config_get(config_obj: Any, key: str, default: Any) -> Any:
    if isinstance(config_obj, dict):
        return config_obj.get(key, default)
    return getattr(config_obj, key, default)


def parse_iso_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO8601 timestamp string into a timezone-aware UTC datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_preferences(config_obj: Any = None) -> Dict[str, Any]:
    """Return canonical default movement preferences from config."""
    cfg = config_obj if config_obj is not None else Config
    return {
        'preferred_distance_unit': str(
            _config_get(cfg, 'DEFAULT_DISTANCE_UNIT', 'km')
        ).lower(),
        'walking_speed_kmh': float(
            _config_get(cfg, 'DEFAULT_WALKING_SPEED_KMH', _config_get(cfg, 'WALKING_SPEED_KMH', 5.0))
        ),
        'running_easy_speed_kmh': float(
            _config_get(cfg, 'DEFAULT_RUNNING_EASY_SPEED_KMH', 9.5)
        ),
        'running_race_speed_kmh': float(
            _config_get(cfg, 'DEFAULT_RUNNING_RACE_SPEED_KMH', 12.5)
        ),
        'movement_prefs_updated_at': None,
    }


def normalise_distance_unit(unit: Any, fallback: str = 'km') -> str:
    if not isinstance(unit, str):
        return fallback
    candidate = unit.strip().lower()
    if candidate in DISTANCE_UNITS:
        return candidate
    return fallback


def validate_preferences_payload(
    payload: Dict[str, Any],
    config_obj: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Validate a PATCH payload and return (normalised_data, field_errors)."""
    defaults = default_preferences(config_obj)
    normalised: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    if 'preferred_distance_unit' in payload:
        unit = payload.get('preferred_distance_unit')
        unit_norm = normalise_distance_unit(unit, fallback='')
        if unit_norm not in DISTANCE_UNITS:
            errors['preferred_distance_unit'] = "Must be 'km' or 'mi'."
        else:
            normalised['preferred_distance_unit'] = unit_norm

    for field, (min_val, max_val) in SPEED_LIMITS.items():
        if field not in payload:
            continue

        raw = payload.get(field)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors[field] = 'Must be a numeric value.'
            continue

        if value < min_val or value > max_val:
            errors[field] = f'Must be between {min_val:.1f} and {max_val:.1f} km/h.'
            continue

        normalised[field] = value

    client_updated_raw = payload.get('client_updated_at')
    if client_updated_raw is not None:
        client_updated = parse_iso_timestamp(client_updated_raw)
        if client_updated is None:
            errors['client_updated_at'] = 'Must be a valid ISO8601 timestamp.'
        else:
            normalised['client_updated_at'] = client_updated

    # Cross-field validation with stable defaults for omitted values.
    easy_speed = float(normalised.get('running_easy_speed_kmh', defaults['running_easy_speed_kmh']))
    race_speed = float(normalised.get('running_race_speed_kmh', defaults['running_race_speed_kmh']))
    if race_speed < easy_speed:
        errors['running_race_speed_kmh'] = 'Must be greater than or equal to running_easy_speed_kmh.'

    return normalised, errors


def build_user_preferences(user: Any = None, config_obj: Any = None) -> Dict[str, Any]:
    """Build canonical preferences from defaults overlaid by user settings."""
    prefs = default_preferences(config_obj)

    if user is not None:
        if getattr(user, 'preferred_distance_unit', None):
            prefs['preferred_distance_unit'] = normalise_distance_unit(
                user.preferred_distance_unit,
                prefs['preferred_distance_unit'],
            )

        for field in SPEED_LIMITS:
            value = getattr(user, field, None)
            if value is not None:
                prefs[field] = float(value)

        updated_at = getattr(user, 'movement_prefs_updated_at', None)
        if updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            prefs['movement_prefs_updated_at'] = updated_at.astimezone(timezone.utc).isoformat()

    # Keep preferences internally coherent even if historical rows are malformed.
    if prefs['running_race_speed_kmh'] < prefs['running_easy_speed_kmh']:
        prefs['running_race_speed_kmh'] = prefs['running_easy_speed_kmh']

    return prefs


def resolve_request_movement_context(
    request_data: Dict[str, Any],
    user: Any = None,
    config_obj: Any = None,
) -> Dict[str, Any]:
    """Resolve travel profile, unit and effective speed for one route request."""
    prefs = build_user_preferences(user=user, config_obj=config_obj)

    travel_profile = str(request_data.get('travel_profile') or 'walking').strip().lower()
    if travel_profile not in TRAVEL_PROFILES:
        raise ValueError(
            "Invalid travel_profile. Must be one of: walking, running_easy, running_race."
        )

    requested_unit = request_data.get('distance_unit')
    if requested_unit is None:
        distance_unit = normalise_distance_unit(
            prefs['preferred_distance_unit'],
            fallback='km',
        )
    else:
        if not isinstance(requested_unit, str):
            raise ValueError("Invalid distance_unit. Must be one of: km, mi.")
        unit_candidate = requested_unit.strip().lower()
        if unit_candidate not in DISTANCE_UNITS:
            raise ValueError("Invalid distance_unit. Must be one of: km, mi.")
        distance_unit = unit_candidate

    speed_field = PROFILE_TO_SPEED_FIELD[travel_profile]
    speed_kmh = float(prefs[speed_field])

    return {
        'travel_profile': travel_profile,
        'distance_unit': distance_unit,
        'effective_speed_kmh': speed_kmh,
        'activity': PROFILE_TO_ACTIVITY[travel_profile],
        'preferences': prefs,
    }


def km_to_display(distance_km: float, unit: str) -> float:
    unit_norm = normalise_distance_unit(unit)
    if unit_norm == 'mi':
        return float(distance_km) / KM_PER_MILE
    return float(distance_km)


def speed_kmh_to_display(speed_kmh: float, unit: str) -> float:
    unit_norm = normalise_distance_unit(unit)
    if unit_norm == 'mi':
        return float(speed_kmh) / KM_PER_MILE
    return float(speed_kmh)


def speed_unit_label(unit: str) -> str:
    return 'mph' if normalise_distance_unit(unit) == 'mi' else 'km/h'


def pace_text_from_speed(speed_kmh: float, unit: str) -> str:
    unit_norm = normalise_distance_unit(unit)
    speed = float(speed_kmh)
    if speed <= 0:
        return f"n/a min/{unit_norm}"

    pace_minutes = (60.0 / speed) * (KM_PER_MILE if unit_norm == 'mi' else 1.0)
    whole = int(pace_minutes)
    seconds = int(round((pace_minutes - whole) * 60.0))

    if seconds == 60:
        whole += 1
        seconds = 0

    return f"{whole}:{seconds:02d} min/{unit_norm}"
