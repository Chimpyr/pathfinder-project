"""Tests for /api/loop demo visualisation payload behavior."""

from dataclasses import dataclass

import pytest
from flask import Flask

import app.routes as routes_module
from app.routes import main


@dataclass
class DummyCandidate:
    route: list
    distance: float
    distance_km: float
    deviation: float
    deviation_percent: float
    scenic_cost: float
    quality_score: float
    algorithm: str
    label: str
    colour: str
    metadata: dict


class DummyRouteFinder:
    """Small route finder stub for deterministic API tests."""

    def __init__(self, graph):
        self.graph = graph

    def find_loop_route(self, **kwargs):
        loop_demo_context = kwargs.get("loop_demo_context")
        if loop_demo_context is not None:
            loop_demo_context.setdefault("frames", []).append(
                {
                    "event": "solver_started",
                    "target_distance_m": kwargs.get("target_distance_m", 0),
                }
            )

        return [
            DummyCandidate(
                route=[1, 2, 3, 1],
                distance=6000.0,
                distance_km=6.0,
                deviation=0.02,
                deviation_percent=2.0,
                scenic_cost=0.321,
                quality_score=0.88,
                algorithm="geometric",
                label="Best Match",
                colour="#3B82F6",
                metadata={},
            )
        ]

    def estimate_route_time(self, **kwargs):
        return 1200


class DummyGraph:
    def __init__(self):
        self.nodes = {1: {}, 2: {}, 3: {}}


@pytest.fixture
def patch_loop_api_dependencies(monkeypatch):
    """Patch expensive dependencies for fast deterministic endpoint tests."""

    monkeypatch.setattr(
        routes_module,
        "_resolve_movement_context",
        lambda _data: {
            "distance_unit": "km",
            "effective_speed_kmh": 5.0,
            "travel_profile": "walking",
            "activity": "walking",
            "preferences": {"movement_prefs_updated_at": None},
        },
    )

    monkeypatch.setattr(
        routes_module,
        "_resolve_lighting_context",
        lambda _data, _start, _end=None: {
            "lighting_context": "night",
            "source": "test",
            "routing_datetime_utc": "2026-03-31T00:00:00Z",
        },
    )

    monkeypatch.setattr(
        routes_module.GraphManager,
        "get_graph_for_route",
        staticmethod(lambda *_args, **_kwargs: DummyGraph()),
    )

    monkeypatch.setattr(routes_module, "RouteFinder", DummyRouteFinder)

    monkeypatch.setattr(
        routes_module.MapRenderer,
        "route_to_coords",
        staticmethod(lambda _graph, _route: [[51.45, -2.58], [51.451, -2.579]]),
    )


@pytest.fixture
def app_factory():
    def _create(debug_enabled):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            DEBUG=debug_enabled,
            VERBOSE_LOGGING=False,
            ASYNC_MODE=False,
            TILE_SIZE_KM=15,
            TILE_OVERLAP_KM=2,
            LOOP_SOLVER_ALGORITHM="GEOMETRIC",
            LOOP_DEMO_MAX_FRAMES=32,
            WSM_DEFAULT_WEIGHTS={
                "distance": 1.0,
                "greenness": 0.0,
                "water": 0.0,
                "quietness": 0.0,
                "social": 0.0,
                "slope": 0.0,
            },
        )
        app.register_blueprint(main)
        return app

    return _create


def _demo_payload():
    return {
        "start_lat": 51.4545,
        "start_lon": -2.5879,
        "distance_km": 6.0,
        "directional_bias": "none",
        "demo_visualisation": True,
        "use_wsm": True,
        "weights": {
            "distance": 100,
            "greenness": 0,
            "water": 0,
            "quietness": 0,
            "social": 0,
            "slope": 0,
        },
    }


def test_loop_demo_disabled_when_debug_false(app_factory, patch_loop_api_dependencies):
    app = app_factory(False)
    client = app.test_client()

    response = client.post("/api/loop", json=_demo_payload())

    assert response.status_code == 200
    data = response.get_json()
    assert data["loop_demo"]["enabled"] is False
    assert data["loop_demo"]["reason"] == "debug_disabled"
    assert data["loop_demo"]["frame_count"] == 0
    assert data["loop_demo"]["frames"] == []


def test_loop_demo_enabled_when_debug_true(app_factory, patch_loop_api_dependencies):
    app = app_factory(True)
    client = app.test_client()

    response = client.post("/api/loop", json=_demo_payload())

    assert response.status_code == 200
    data = response.get_json()
    assert data["loop_demo"]["enabled"] is True
    assert data["loop_demo"]["frame_count"] >= 1
    assert isinstance(data["loop_demo"]["frames"], list)
    assert data["loop_demo"]["frames"][0]["event"] == "solver_started"
