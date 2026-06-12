from __future__ import annotations

from pathlib import Path

from .constants import SERVO_RANGES, SERVO_NAMES
from .io_utils import read_csv


def load_servo_limits(config_dir: str | Path) -> dict[str, tuple[float, float]]:
    path = Path(config_dir) / "servo_limits.csv"
    limits = dict(SERVO_RANGES)
    if path.is_file():
        for row in read_csv(path):
            name = row["servo_name"]
            if name in limits:
                default_lo, default_hi = SERVO_RANGES[name]
                lo = max(default_lo, float(row["min"]))
                hi = min(default_hi, float(row["max"]))
                limits[name] = (lo, hi) if lo <= hi else (default_lo, default_hi)
    return limits


def clamp_servo_values(rows: list[dict], limits: dict[str, tuple[float, float]]) -> list[dict]:
    out = []
    for row in rows:
        new = dict(row)
        for name in SERVO_NAMES:
            lo, hi = limits.get(name, (-1.0, 1.0))
            new[name] = round(max(lo, min(hi, float(new[name]))), 6)
        out.append(new)
    return out


def smooth_trajectory(rows: list[dict], beta: float = 0.75, max_delta: float = 0.14) -> list[dict]:
    if not rows:
        return []
    beta = max(0.0, min(1.0, float(beta)))
    max_delta = max(0.0, float(max_delta))

    out = []
    prev = {name: float(rows[0][name]) for name in SERVO_NAMES}
    for idx, row in enumerate(rows):
        new = dict(row)
        for name in SERVO_NAMES:
            target = float(row[name])
            if idx == 0:
                value = target
            else:
                value = beta * target + (1.0 - beta) * prev[name]
                delta = value - prev[name]
                if max_delta > 0 and abs(delta) > max_delta:
                    value = prev[name] + max_delta * (1.0 if delta > 0 else -1.0)
            new[name] = round(value, 6)
            prev[name] = value
        out.append(new)
    return out
