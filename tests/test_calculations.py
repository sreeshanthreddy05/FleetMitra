from datetime import datetime, timezone

import pytest

from calculations import haversine, derived_speed, estimate_eta


def test_same_point():
    assert haversine(17, 78, 17, 78) == 0


def test_known_distance():
    assert haversine(0, 0, 0, 1) == pytest.approx(111194.93, rel=1e-5)
    assert haversine(0, 0, 0, 180) == pytest.approx(20015086.8, rel=1e-5)


@pytest.mark.parametrize("point", [(91, 0, 0, 0), (0, 181, 0, 0), (0, 0, -91, 0),
                                    (float("nan"), 0, 0, 0), (True, 0, 0, 0), ("1", 0, 0, 0),
                                    (10**400, 0, 0, 0)])
def test_invalid_coordinates(point):
    with pytest.raises(ValueError):
        haversine(*point)


def test_speed():
    assert derived_speed(100, 10) == 36
    assert derived_speed(100, 0) is None
    assert derived_speed(100, -10) is None
    assert derived_speed(10000, 1) is None


def test_moving_eta():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    eta = estimate_eta(1000, [36, 36, 36], now=now)
    assert eta["method"] == "FALLBACK"
    assert eta["duration_seconds"] == 100
    assert eta["arrival_time"] == "2026-01-01T00:01:40+00:00"


@pytest.mark.parametrize("samples", [[], [0], [1], [0, 50, 50]])
def test_stationary_eta(samples):
    eta = estimate_eta(1000, samples)
    assert eta["status"] == "WAITING_FOR_MOVEMENT"
    assert eta["duration_seconds"] is None


def test_arrived_eta():
    eta = estimate_eta(10, [0])
    assert eta["status"] == "ARRIVED"
    assert eta["remaining_distance_m"] == 0


def test_road_route_eta():
    eta = estimate_eta(1000, [36], {"distance_m": 1500, "duration_seconds": 180})
    assert eta["method"] == "ROAD_ROUTE"
    assert eta["duration_seconds"] == 180
    assert eta["remaining_distance_m"] == 1500
    assert eta["straight_line_distance_m"] == 1000


def test_stale_eta():
    assert estimate_eta(1000, [36], stale=True)["status"] == "WAITING_FOR_GPS"
