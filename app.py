"""Run with python app.py. Tests use create_app with a temporary SQLite path."""
import os
import sqlite3
import json
import hashlib
import socket
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Make the documented bare command use this project's installed dependencies.
if __name__ == '__main__':
    project_python = ROOT / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if project_python.exists() and Path(sys.prefix).resolve() != project_python.parent.parent.resolve():
        raise SystemExit(subprocess.call([str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]]))

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.serving import ThreadedWSGIServer

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
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    if test_config:
        app.config.update(test_config)
    app.json.sort_keys = False
    @app.url_defaults
    def version_assets(endpoint, values):
        if endpoint == 'static' and 'filename' in values:
            asset = Path(app.static_folder) / values['filename']
            if asset.is_file():
                values.setdefault('v', hashlib.sha256(asset.read_bytes()).hexdigest()[:12])

    @app.after_request
    def revalidate_dashboard(response):
        if request.endpoint == 'static' or response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
        return response
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


class ExclusiveServer(ThreadedWSGIServer):
    """Windows SO_REUSEADDR otherwise permits old and new servers on one port."""
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    host = os.getenv('FLEET_HOST', '127.0.0.1')
    port = int(os.getenv('FLEET_PORT', '5000'))
    # Reserve the port before opening the database or reconciling active trips.
    print(f'FleetMitra project: {ROOT}\nPython: {sys.executable}', flush=True)
    print(f'Database: {settings()["DATABASE"]}\nOpening http://{host}:{port}', flush=True)
    print('If the port is occupied, stop the existing server before restarting.', flush=True)
    server = ExclusiveServer(host, port, None)
    try:
        server.app = create_app()
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
