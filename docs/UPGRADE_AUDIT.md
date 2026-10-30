# Upgrade audit — 30 October 2026

Before implementation, the existing Flask factory, all API modules, SQLite schema, tracking/routing services, calculations, simulator, HTML/CSS/JavaScript, tests, README and firmware were inspected. No repository-specific AGENTS.md was found. The directory is not a Git checkout.

Baseline command: `venv\Scripts\python.exe -m pytest -q`.

**91 passed in 6.36s**, before major edits. The sandbox disallowed pytest's temporary directories; the successful run used approved access outside the sandbox.

Existing strengths retained: strict JSON/GPS validation, UTC normalization, idempotent timestamp retries, atomic distance/geofence updates, jitter anchor, one-active-trip index, circular transition state, routing fallback, FM01, local Leaflet, CLI sender and untested future hardware sketch.

Missing review features: selected route persistence, browser-controlled simulation, logical time acceleration, deviation monitoring, general event timeline, persistent admin notifications, audio, arrival summaries and detailed route history.

Source backup: `instance/upgrade-backup/baseline-source.zip`. SQLite backup: `instance/upgrade-backup/baseline.sqlite3`. Existing data is preserved. New tables and nullable/defaulted columns are added idempotently; the original trip status CHECK constraint remains intact. Review trips expose ARRIVED through a completion-status column while legacy trips retain their original manual stop behavior.
