import sqlite3

from app import create_app
from database import SCHEMA


def test_legacy_database_is_preserved_and_upgrade_is_repeatable(tmp_path):
    path = str(tmp_path / "legacy.sqlite3")
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO vehicles VALUES ('FM01','Existing Vehicle','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO locations (vehicle_id,lat,lon,timestamp,received_at,speed_kmh,gps_valid,source) "
               "VALUES ('FM01',17,78,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',0,1,'HARDWARE')")
    db.commit()
    db.close()
    for _ in range(2):
        app = create_app({"TESTING":True,"DATABASE":path,"ROUTING_ENABLED":False})
        client = app.test_client()
        assert client.get("/api/vehicles").json["vehicles"][0]["vehicle_name"] == "Existing Vehicle"
        assert len(client.get("/api/vehicles/FM01/history").json["locations"]) == 1
