"""A GPS-like sender. All tracking logic stays behind POST /api/locations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Permit `python simulator/gps_simulator.py` from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calculations import haversine


def send_reading(base_url, payload, timeout=5):
    request = Request(base_url.rstrip("/") + "/api/locations",
                      data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return response.status, json.load(response)


def simulate(base_url, points, interval=3, loop=False, max_points=None):
    """Retry a failed point without advancing. Loops reverse to avoid teleporting."""
    print("FleetMitra GPS Simulator\nVehicle: FM01\nSource: SIMULATED", flush=True)
    print(f"Backend: {base_url} | Interval: {interval:g}s | Ctrl+C to stop", flush=True)
    index, direction, accepted = 0, 1, 0
    previous_point, previous_time = None, None
    pending = None
    while True:
        point = points[index]
        if pending is None:
            now = datetime.now(timezone.utc)
            speed = 0.0
            if previous_point is not None:
                elapsed = (now - previous_time).total_seconds()
                distance = haversine(previous_point["lat"], previous_point["lon"], point["lat"], point["lon"])
                # Fast playback changes simulated speed, capped at a plausible maximum.
                speed = min(120, distance / max(elapsed, .001) * 3.6)
            pending = {"vehicle_id": "FM01", "lat": point["lat"], "lon": point["lon"],
                       "timestamp": now.isoformat().replace("+00:00", "Z"),
                       "speed_kmh": round(speed, 1), "gps_valid": True, "source": "SIMULATED"}
        print(f"Sending {index + 1}/{len(points)}: Latitude {pending['lat']:.6f} | "
              f"Longitude {pending['lon']:.6f} | Speed {pending['speed_kmh']:.1f} km/h", flush=True)
        try:
            status, response = send_reading(base_url, pending)
            if not response.get("accepted"):
                raise ValueError("Backend did not accept the point")
            eta = response["vehicle"].get("eta")
            print(f"Server response: {status} OK | "
                  f"{'duplicate retry' if response.get('duplicate') else 'stored'} | "
                  f"ETA: {eta['status'] if eta else 'no active trip'}", flush=True)
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            print(f"Server response: {error.code} {detail}", flush=True)
            if 400 <= error.code < 500:
                print("Reading rejected. Check API settings and ensure only one GPS sender is running.", flush=True)
                return 1
            time.sleep(interval)
            continue
        except (URLError, OSError, ValueError, KeyError) as error:
            print(f"Backend unavailable: {error}. Retrying this same reading...", flush=True)
            time.sleep(interval)
            continue
        previous_point = point
        previous_time = datetime.fromisoformat(pending["timestamp"])
        pending = None
        accepted += 1
        if max_points and accepted >= max_points:
            break
        next_index = index + direction
        if not 0 <= next_index < len(points):
            if not loop:
                break
            direction *= -1
            next_index = index + direction
        index = next_index
        time.sleep(interval)
    print(f"Simulation complete: {accepted} readings accepted.", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description="FleetMitra GPS simulator (no hardware required)")
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--route", type=Path, default=Path(__file__).with_name("sample_route.json"))
    parser.add_argument("--interval", type=float, default=3, help="Seconds between readings (default: 3)")
    parser.add_argument("--loop", action="store_true", help="Drive back and forth continuously")
    parser.add_argument("--max-points", type=int, help="Stop after this many accepted readings")
    args = parser.parse_args()
    if not 0 < args.interval < 3600:
        parser.error("--interval must be between 0 and 3600 seconds")
    if args.max_points is not None and args.max_points < 1:
        parser.error("--max-points must be positive")
    try:
        data = json.loads(args.route.read_text(encoding="utf-8"))
        points = data["points"]
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("Route must contain at least two points")
        for point in points:
            haversine(point["lat"], point["lon"], point["lat"], point["lon"])
        return simulate(args.url, points, args.interval, args.loop, args.max_points)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Invalid route: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
