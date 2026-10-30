"""Run with python app.py. Tests use create_app with a temporary SQLite path."""
import os
import sqlite3
import json
from pathlib import Path

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import HTTPException

from config import settings
from database import close_db, get_db, init_db
from routes import geofence_routes, location_routes, trip_routes
from services.routing_service import RoutingService
from services.simulation_service import SimulationEngine
from routes import operations_routes
from routes import history_routes
from routes import driver_routes, destination_routes
from services.geocoding_service import Geocoder
from validation import APIError


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(settings())
    if test_config:
        app.config.update(test_config)
    app.json.sort_keys = False
    app.teardown_appcontext(close_db)
    app.extensions["routing"] = RoutingService(app.config)
    app.extensions['geocoder']=Geocoder(app.config)
    for blueprint in (location_routes.bp, trip_routes.bp, geofence_routes.bp, operations_routes.bp,history_routes.bp,driver_routes.bp,destination_routes.bp):
        app.register_blueprint(blueprint)

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        get_db().execute("SELECT 1").fetchone()
        return jsonify(status="ok", database="connected")

    @app.get("/api/demo-config")
    def demo_config():
        # Presets fill controls only; they never create readings or tracking state.
        route = json.loads((Path(app.root_path) / "simulator/sample_route.json").read_text(encoding="utf-8"))
        return jsonify(name=route["name"], destination=route["destination"], geofence=route["geofence"])

    @app.errorhandler(APIError)
    def api_error(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.exception("Database request failed")
        return jsonify(error="Database unavailable; please retry"), 503

    with app.app_context():
        init_db()
    app.extensions["simulation"] = SimulationEngine(app)
    return app


if __name__ == "__main__":
    create_app().run(host=os.getenv("FLEET_HOST", "127.0.0.1"),
                     port=int(os.getenv("FLEET_PORT", "5000")), debug=False)
