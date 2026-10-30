import re
import socket

import pytest

from app import ExclusiveServer


def test_dashboard_delivers_complete_ordered_asset_bundle(client):
    response = client.get('/')
    html = response.get_data(as_text=True)
    scripts = re.findall(r'<script defer src="([^"]+)"', html)
    names = [url.split('/static/')[1].split('?')[0] for url in scripts]
    assert names.index('js/navigation_geometry.js') < names.index('js/map.js')
    assert names.index('js/review.js') < names.index('js/workspace.js')
    assert names.index('js/workspace.js') < names.index('js/search.js')
    assert names.index('js/search.js') < names.index('js/journey_extensions.js')
    assert 'Demo Scenarios' not in html
    assert 'Operations control' not in html
    assert 'href="/drivers"' in html and 'id="home-shortcut"' in html
    assert 'must-revalidate' in response.headers['Cache-Control']
    for url in scripts:
        assert re.search(r'\?v=[0-9a-f]{12}$', url)
        assert client.get(url).status_code == 200


def test_asset_version_changes_when_content_changes(app, tmp_path):
    app.static_folder = str(tmp_path)
    asset = tmp_path / 'probe.js'
    asset.write_text('first')
    from flask import url_for
    with app.test_request_context():
        first = url_for('static', filename='probe.js')
        asset.write_text('other')  # same length: content, not size, determines version
        second = url_for('static', filename='probe.js')
    assert first != second


def test_templates_reload_without_restarting_server(app, tmp_path):
    from jinja2 import FileSystemLoader
    app.jinja_loader = FileSystemLoader(tmp_path)
    page = tmp_path / 'index.html'
    page.write_text('first version')
    client = app.test_client()
    assert client.get('/').text == 'first version'
    page.write_text('updated version')
    import os
    stat = page.stat()
    os.utime(page, (stat.st_atime, stat.st_mtime + 2))
    assert client.get('/').text == 'updated version'


def test_second_server_cannot_share_existing_port():
    first = ExclusiveServer('127.0.0.1', 0, None)
    try:
        with pytest.raises(SystemExit):
            ExclusiveServer('127.0.0.1', first.port, None)
        with socket.socket() as competing:
            competing.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError):
                competing.bind(('127.0.0.1', first.port))
    finally:
        first.server_close()
