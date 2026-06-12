from __future__ import annotations

import json
from pathlib import Path

from .constants import (
    DEFAULT_NEUTRAL_REST,
    DEFAULT_PINYIN_TO_VISEME,
    DEFAULT_VISEME_TARGETS,
    MOUTH_CSV_NAMES,
    MOUTH_VALUE_RANGES,
    SERVO_RANGES,
    SERVO_NAMES,
    SHAPE_LABELS,
    VISEME_TABLE,
)
from .io_utils import write_csv, write_json


def ensure_default_configs(root: str | Path, config_dir: str | Path) -> dict[str, str]:
    root = Path(root)
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    written = {}
    pinyin_path = config_dir / "pinyin_to_viseme.json"
    if not pinyin_path.is_file():
        write_json(pinyin_path, DEFAULT_PINYIN_TO_VISEME)
        written["pinyin_to_viseme"] = str(pinyin_path)

    neutral_path = config_dir / "neutral_rest.csv"
    if not neutral_path.is_file():
        neutral = load_existing_neutral(root)
        rows = [
            {
                "servo_id": idx,
                "servo_name": SERVO_NAMES[idx],
                "value": round(float(neutral.get(idx, DEFAULT_NEUTRAL_REST[idx])), 6),
            }
            for idx in range(16)
        ]
        write_csv(neutral_path, rows, ["servo_id", "servo_name", "value"])
        written["neutral_rest"] = str(neutral_path)

    pose_path = config_dir / "neutral_viseme_pose_final.csv"
    if not pose_path.is_file():
        targets = load_existing_viseme_targets(root)
        rows = []
        for idx in range(8):
            row = {
                "viseme_id": idx,
                "phonemes": ",".join(VISEME_TABLE[idx]),
            }
            targets[idx] = clamp_mouth_values(targets[idx])
            for name, value in zip(MOUTH_CSV_NAMES, targets[idx]):
                row[name] = round(float(value), 6)
            rows.append(row)
        write_csv(pose_path, rows, ["viseme_id", "phonemes", *MOUTH_CSV_NAMES])
        written["neutral_viseme_pose_final"] = str(pose_path)

    meta_path = config_dir / "viseme_meta.csv"
    if not meta_path.is_file():
        targets = load_existing_viseme_targets(root)
        rows = [
            {
                "viseme_id": idx,
                "phonemes": ",".join(VISEME_TABLE[idx]),
                "aperture": round(max(0.0, min(1.0, float(targets[idx][0]))), 6),
                "shape_label": SHAPE_LABELS[idx],
            }
            for idx in range(8)
        ]
        write_csv(meta_path, rows, ["viseme_id", "phonemes", "aperture", "shape_label"])
        written["viseme_meta"] = str(meta_path)

    limits_path = config_dir / "servo_limits.csv"
    if not limits_path.is_file():
        rows = [
            {"servo_name": name, "min": SERVO_RANGES[name][0], "max": SERVO_RANGES[name][1]}
            for name in SERVO_NAMES
        ]
        write_csv(limits_path, rows, ["servo_name", "min", "max"])
        written["servo_limits"] = str(limits_path)

    return written


def load_existing_neutral(root: Path) -> dict[int, float]:
    neutral = dict(DEFAULT_NEUTRAL_REST)
    path = root / "neutral_rest.json"
    if not path.is_file():
        pose_path = root / "viseme_poses_6d.json"
        if pose_path.is_file():
            data = json.loads(pose_path.read_text(encoding="utf-8"))
            raw = data.get("neutral_rest")
            if raw:
                for key, value in raw.items():
                    neutral[int(key)] = float(value)
        return neutral

    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("neutral_rest", data)
    for key, value in raw.items():
        neutral[int(key)] = float(value)
    return neutral


def load_existing_viseme_targets(root: Path) -> dict[int, list[float]]:
    targets = {idx: list(values) for idx, values in DEFAULT_VISEME_TARGETS.items()}
    path = root / "viseme_poses_6d.json"
    if not path.is_file():
        return targets

    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("viseme_targets", data)
    for idx in range(8):
        if str(idx) in raw:
            values = [float(v) for v in raw[str(idx)]]
            if len(values) == 6:
                targets[idx] = clamp_mouth_values(values)
    return targets


def clamp_mouth_values(values: list[float]) -> list[float]:
    return [
        max(lo, min(hi, float(value)))
        for value, (lo, hi) in zip(values, MOUTH_VALUE_RANGES)
    ]
