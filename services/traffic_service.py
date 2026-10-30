"""Reproducible comparison-only traffic; not live traffic or measured GPS speed."""
import hashlib
import json


def simulated_traffic(geometry, duration, seed):
    digest = hashlib.sha256((str(seed) + json.dumps(geometry, sort_keys=True)).encode()).digest()
    level, factor = [("Low", .05), ("Moderate", .25), ("Heavy", .60)][digest[0] % 3]
    delay = round(duration * factor, 1)
    return {"label": "SIMULATED TRAFFIC", "level": level, "delay_factor": factor,
            "delay_seconds": delay, "adjusted_duration_seconds": round(duration + delay, 1), "seed": str(seed)}
