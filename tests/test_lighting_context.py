"""Unit tests for request-scoped lighting context resolution."""

from app.services.routing.lighting_context import resolve_request_lighting_context


def test_lighting_context_override_is_honoured():
    result = resolve_request_lighting_context(
        {
            'lighting_context_override': 'night',
            'routing_datetime_utc': '2026-03-29T12:00:00Z',
        },
        start_point=(51.4545, -2.5879),
        end_point=(51.4550, -2.5790),
    )

    assert result['lighting_context'] == 'night'
    assert result['source'] == 'override'


def test_auto_context_midday_is_daylight_for_bristol_fixture():
    result = resolve_request_lighting_context(
        {'routing_datetime_utc': '2026-06-21T12:00:00Z'},
        start_point=(51.4545, -2.5879),
        end_point=(51.4550, -2.5790),
    )

    assert result['lighting_context'] == 'daylight'
    assert result['source'] == 'auto'
    assert result['solar_meta'] is not None


def test_auto_context_after_midnight_is_night_for_bristol_fixture():
    result = resolve_request_lighting_context(
        {'routing_datetime_utc': '2026-03-29T00:30:00Z'},
        start_point=(51.4545, -2.5879),
        end_point=(51.4550, -2.5790),
    )

    assert result['lighting_context'] == 'night'
    assert result['source'] == 'auto'
