# FleetMitra saved-work audit — 30 October 2026

## Conclusion

The final feature implementation is saved in **D:\College Projects\CBP IOT\Fleet Mitra**. No missing core software feature was found in the inspected requirements, source, tests and fresh browser workflow. No application code needed replacement. Documentation contained outdated Git/server statements; this audit corrects them.

The likely source of the apparent missing work is **different SQLite datasets**, not a different software branch:

| Database | Trips at audit start | Drivers at audit start |
| --- | ---: | ---: |
| instance/fleet_mitra.sqlite3 (default) | 1 | 0 |
| instance/final-features-qa.sqlite3 (final review) | 3 | 1 |
| instance/final-review-qa.sqlite3 | 4 | Driver schema not yet migrated |
| instance/navigation-qa.sqlite3 | 3 | Driver schema not yet migrated |
| instance/review-qa-20261030.sqlite3 | 2 | Driver schema not yet migrated |

Older isolated QA databases need not have the latest schema until opened by the current application. This audit did not migrate, merge, reset or delete them. All five passed read-only SQLite integrity checks and had zero foreign-key violations. The browser audit added one genuine simulation trip (#4) to the final-feature review database; existing trips remain.

## Git, directory and saved files

- `Get-Location` and `git worktree list` identify the exact directory above.
- Branch: **main**. Only one local branch and worktree were listed. The parent CBP IOT directory contains only this FleetMitra project. No evidence of work on another branch or sibling checkout was found; this is not a whole-computer filesystem search.
- Initial HEAD: **f59f113b960a75f2e8795b4a3bee765aaf35b9d0**, `Initial commit - Complete FleetMitra IoT Project`, created 30 October at 22:26:43 +05:30. It contains 102 files, including the driver/destination modules and their tests.
- Initial `git status --porcelain=v1 --untracked-files=all` was empty. No uncommitted or untracked project files were present. Git cannot inspect unsaved editor buffers; this audit verifies the saved files that actually execute.
- Local origin/main also pointed at f59f113. No fetch or push was performed, so this describes the local remote-tracking ref, not a newly queried GitHub state.
- Database files, keys, environment secrets, venv and caches are ignored and remain outside the commit.
- The previous progress report's no-Git statement describes an earlier point in time and is superseded by this audit. The audit changes are committed locally only after verification; obtain their hash with `git log -1 --format=%H`.

## Requirement coverage

| Requirement group | Implementation classification | Evidence and qualification |
| --- | --- | --- |
| Spacious dashboard, sidebar, advanced disclosures, responsive history | Implemented | workspace CSS/JS and templates; live dashboard and mobile history rendered. Visual quality is subjective; not every zoom/device was retested. |
| Exact Home, free manual endpoints, swap and search | Implemented | config stores 17.415666, 78.573060; actual browser markers matched exact Home and Photon-selected Uppal. Home is not a forced origin. |
| Road alternatives, comparison, simulated traffic | Implemented | Live OSRM returned one genuine route with explicit fewer-than-three explanation; no fabricated alternatives. |
| Blue outlined navigation, grey progress, rotating vehicle | Implemented | map.js and geometry tests; real navigation/map rendered during fresh trip. Historical route layers use saved geometry. |
| Follow Vehicle and Fit Entire Route | Implemented | Follow enabled in live trip and settled at zoom 17; manual zoom disabled follow. Fit is a separate control. Existing JS tests cover gestures/state. |
| Search provider, debounce, keyboard, failures | Implemented | Photon proxy with bounded requests/cache; live Uppal and Habsiguda suggestions selected; existing tests cover provider failures and coordinate selection. |
| Map clarity/layers/attribution | Implemented with external dependencies | Bundled Leaflet; OSM default; optional localhost Stadia layer with supported high-DPI URL and fallback. Standard map rendered with readable labels. Physical high-DPI and all zoom/layer combinations not freshly retested. |
| Automatic rerouting and deviation alerts | Implemented | Fresh trip #4 persisted ROUTE_DEVIATION and REROUTE_ACCEPTED; popup rendered. Demonstration explicitly used a synthetic offset, followed by a genuine replacement road route. |
| Dynamic destination changes | Implemented | Proposals/revisions/expiry/idempotency; fresh moving stale proposals safely refreshed; paused activation succeeded in same trip, followed by arrival at new destination. Moving activation and concurrency are additionally covered by passing existing tests. |
| Driver registration, edit, validation, assignment, status, privacy | Implemented | Encrypted private fields, masked public fields, transactional eligibility, snapshot storage; tests passed. Fresh browser showed assigned driver On Trip, then Available and updated real statistics. Registration/edit mutations were not repeated in this audit; tests and prior browser evidence cover them. |
| Persistent trips, GPS samples, lifecycle, events, original/replacement routes | Implemented | Fresh completed trip, actual Flask restart and exact row-digest comparison across six tables; all matched. Existing tests cover active recovery, cancellation, duplicates and previous-trip preservation. |
| History filters/pagination/details/driver history/CSV/JSON | Implemented | Backend + templates + tests; browser reopened #4 with original Home, final Habsiguda, driver, events and 565 positions. Export responses freshly validated over HTTP. |
| ESP32 compatibility and hardware | Software interface preserved; physical verification incomplete | No firmware changes. Existing location ingestion tests pass; physical GPS/ESP32, speaker and touchscreen remain untested. |
| Git/startup documentation | Initially partial/outdated; corrected | Clear database choice, saved-code audit and current local Git state added. |

No requested core software module was found missing. The application remains a single-vehicle localhost prototype, not a production multi-user fleet deployment. Legacy trips without drivers intentionally remain valid; dashboard trips require an eligible driver. Public routing, tiles and search can fail or throttle. Strict 10 m destination-route validation can require refreshed options while moving; no stale route is forced.

## Fresh verification

- Complete existing suite: **200 passed, 0 failed, 0 skipped, 31.42 seconds**. No tests removed, weakened or added for documentation-only changes.
- All static JavaScript files passed `node --check`; `git diff --check` passed.
- Browser: sample driver selected; searched Uppal origin; exact Home destination; genuine OSRM route; Start; Follow; Habsiguda search and route proposals; stale activation refresh; controlled deviation and automatic replacement; pause; successful destination activation; resume at explicitly selected 16x; completed at Habsiguda.
- Trip #4: **4.92 km, 7m 23s logical duration, 39.9 km/h average, 40 km/h maximum, 565 recorded positions, one destination change, one deviation, one accepted reroute**. Driver and trip ID were retained. Driver returned to Available, with 4 total trips and 3 arrivals.
- Restarted Flask against the same review database after completion. SHA-256 digests of all ordered rows in trips, drivers, locations, trip_events, trip_route_versions and destination_proposals matched exactly before/after. Browser then displayed #4 COMPLETED / ARRIVED and its persisted timeline.
- Desktop map/history rendered; mobile history at 390x844 had document width 375 px, with the wide table scrolling within its container. Browser error-log inspection returned no errors. Viewport override restored.
- Screenshot: [post-restart completed trip](docs/audit-trip-4.png). Earlier screenshots are retained as historical evidence, not represented as new tests.

## Exact files changed by this audit

1. `FLEETMITRA_AUDIT_REPORT.md` — this new report.
2. `README.md` — audit link and stable review-configuration wording.
3. `PROJECT_DEMO_GUIDE.md` — correct Git information and explicit default/review database distinction.
4. `FLEETMITRA_PROGRESS_REPORT.md` — current audit results superseding historical Git statements.
5. `docs/audit-trip-4.png` — fresh browser evidence.

Application source, tests, requirements and firmware are unchanged. Runtime records are saved in the ignored review database, including the new audit trip; they are not committed or fabricated.

## Launch the verified review dataset

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
$env:FLEET_DATABASE='instance/final-features-qa.sqlite3'
$env:FLEET_PORT='5004'
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5004. A server using this configuration is left running at audit completion. Use only one process per database. For the default dataset, launch `app.py` in a fresh shell without FLEET_DATABASE/FLEET_PORT overrides; it uses instance/fleet_mitra.sqlite3 on port 5000. Register a driver there if you want to use that dataset. Never replace a database or encryption key to make the UI look populated.

**Status: READY FOR DEMO for the verified software simulation workflow.** Hardware verification and external-provider availability remain qualified above. No GitHub push is authorized or performed by this audit.
