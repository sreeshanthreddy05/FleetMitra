from datetime import datetime, timezone, timedelta

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"),
                       "ROUTING_ENABLED": False, "STALE_AFTER_SECONDS": 86400})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def reading():
    base = datetime.now(timezone.utc) - timedelta(minutes=10)

    def make(seconds=0, **changes):
        data = {"vehicle_id": "FM01", "lat": 17.4124, "lon": 78.4767,
                "timestamp": (base + timedelta(seconds=seconds)).isoformat(),
                "speed_kmh": 30, "gps_valid": True, "source": "SIMULATED"}
        data.update(changes)
        return data
    return make


@pytest.fixture
def destination():
    return {"vehicle_id": "FM01", "destination_lat": 17.4237,
            "destination_lon": 78.4881, "destination_label": "Tank Bund destination"}
