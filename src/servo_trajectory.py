from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .constants import (
    DEFAULT_NEUTRAL_REST,
    DEFAULT_VISEME_TARGETS,
    MOUTH_CSV_NAMES,
    MOUTH_INDICES,
    MOUTH_SERVO_NAMES,
    MOUTH_VALUE_RANGES,
    SERVO_RANGES,
    SERVO_NAMES,
)
from .io_utils import read_csv


def load_viseme_poses(config_dir: str | Path, pose_json_path: str | Path | None = None) -> dict[int, np.ndarray]:
    config_dir = Path(config_dir)
    csv_path = config_dir / "neutral_viseme_pose_final.csv"
    targets = {
        idx: clamp_mouth_array(np.asarray(values, dtype=np.float32))
        for idx, values in DEFAULT_VISEME_TARGETS.items()
    }

    if csv_path.is_file():
        for row in read_csv(csv_path):
            idx = int(row["viseme_id"])
            values = []
            for name in MOUTH_CSV_NAMES:
                values.append(float(row[name]))
            targets[idx] = clamp_mouth_array(np.asarray(values, dtype=np.float32))
        return targets

    if pose_json_path and Path(pose_json_path).is_file():
        data = json.loads(Path(pose_json_path).read_text(encoding="utf-8"))
        raw = data.get("viseme_targets", data)
        for idx in range(8):
            if str(idx) in raw:
                targets[idx] = clamp_mouth_array(np.asarray(raw[str(idx)], dtype=np.float32))
    return targets


def load_neutral_rest(config_dir: str | Path, neutral_json_path: str | Path | None = None) -> dict[int, float]:
    config_dir = Path(config_dir)
    values = {idx: float(value) for idx, value in DEFAULT_NEUTRAL_REST.items()}
    csv_path = config_dir / "neutral_rest.csv"

    if csv_path.is_file():
        for row in read_csv(csv_path):
            idx = int(row["servo_id"])
            values[idx] = clamp_servo_value(SERVO_NAMES[idx], float(row["value"]))
        return values

    if neutral_json_path and Path(neutral_json_path).is_file():
        data = json.loads(Path(neutral_json_path).read_text(encoding="utf-8"))
        raw = data.get("neutral_rest", data)
        for key, value in raw.items():
            idx = int(key)
            values[idx] = clamp_servo_value(SERVO_NAMES[idx], float(value))
    return values


def neutral_mouth_from_rest(neutral_rest: dict[int, float]) -> np.ndarray:
    return clamp_mouth_array(np.asarray([neutral_rest.get(idx, 0.0) for idx in MOUTH_INDICES], dtype=np.float32))


def generate_mouth_trajectory(
    mix_rows: list[dict],
    n_frames: int,
    viseme_poses: dict[int, np.ndarray],
    neutral_mouth: np.ndarray | None = None,
    rms_rows: list[dict] | None = None,
    use_rms_amplitude: bool = True,
    rms_amp_min: float = 0.72,
    rms_amp_max: float = 1.08,
    rms_amp_percentile: float = 0.92,
    rms_amp_smooth_window: int = 3,
) -> list[dict]:
    neutral = clamp_mouth_array(neutral_mouth if neutral_mouth is not None else np.zeros(6, dtype=np.float32))
    frame_rows: list[dict] = []
    active_by_frame = {int(row["frame_id"]): row for row in mix_rows}
    rms_scales = _rms_amplitude_scales(
        rms_rows,
        n_frames,
        amp_min=rms_amp_min,
        amp_max=rms_amp_max,
        percentile=rms_amp_percentile,
        smooth_window=rms_amp_smooth_window,
    ) if use_rms_amplitude else None

    for frame_id in range(int(n_frames)):
        mix = active_by_frame.get(frame_id)
        if mix:
            start_v = int(mix["start_viseme"])
            end_v = int(mix["end_viseme"])
            start = viseme_poses[start_v]
            end = viseme_poses[end_v]
            alpha = float(mix["alpha"])
            mouth = clamp_mouth_array(start * (1.0 - alpha) + end * alpha)
            rms_amp = ""
            if rms_scales is not None:
                rms_amp_value = _protect_constrained_visemes(
                    float(rms_scales[frame_id]),
                    start_v=start_v,
                    end_v=end_v,
                    alpha=alpha,
                )
                mouth = clamp_mouth_array(neutral + (mouth - neutral) * rms_amp_value)
                rms_amp = round(float(rms_amp_value), 6)
            meta = {
                "syllable": mix["syllable"],
                "start_v": start_v,
                "end_v": end_v,
                "alpha": round(alpha, 6),
                "rms_amp": rms_amp,
            }
            time_ms = int(mix["time_ms"])
        else:
            mouth = clamp_mouth_array(neutral)
            meta = {"syllable": "", "start_v": "", "end_v": "", "alpha": "", "rms_amp": ""}
            time_ms = ""

        row = {"frame_id": frame_id, "time_ms": time_ms, **meta}
        for name, value in zip(MOUTH_CSV_NAMES, mouth):
            row[name] = round(float(value), 6)
        frame_rows.append(row)
    return frame_rows


def _rms_amplitude_scales(
    rms_rows: list[dict] | None,
    n_frames: int,
    amp_min: float,
    amp_max: float,
    percentile: float,
    smooth_window: int,
) -> np.ndarray | None:
    if not rms_rows:
        return None

    n_frames = int(n_frames)
    rms_norm = np.zeros(n_frames, dtype=np.float32)
    active = np.zeros(n_frames, dtype=bool)
    for row in rms_rows:
        frame_id = int(row.get("frame_id", 0))
        if 0 <= frame_id < n_frames:
            rms_norm[frame_id] = max(0.0, float(row.get("rms_norm", 0.0)))
            active[frame_id] = int(row.get("active", 0)) == 1

    reference_values = rms_norm[active]
    if len(reference_values) == 0 or float(np.max(reference_values)) <= 0.0:
        reference_values = rms_norm[rms_norm > 0.0]
    if len(reference_values) == 0:
        return np.ones(n_frames, dtype=np.float32)

    percentile = max(0.50, min(0.99, float(percentile)))
    reference = max(1e-6, float(np.percentile(reference_values, percentile * 100.0)))
    energy = np.clip(rms_norm / reference, 0.0, 1.0)
    energy = np.sqrt(energy)

    window = max(1, int(smooth_window))
    if window > 1 and len(energy) > 1:
        kernel = np.ones(window, dtype=np.float32) / float(window)
        energy = np.convolve(energy, kernel, mode="same")

    amp_min = max(0.0, float(amp_min))
    amp_max = max(amp_min, float(amp_max))
    return (amp_min + (amp_max - amp_min) * np.clip(energy, 0.0, 1.0)).astype(np.float32)


def _protect_constrained_visemes(scale: float, start_v: int, end_v: int, alpha: float) -> float:
    alpha = max(0.0, min(1.0, float(alpha)))
    protected = 0.0
    if int(start_v) in {0, 1}:
        protected = max(protected, 1.0 - alpha)
    if int(end_v) in {0, 1}:
        protected = max(protected, alpha)
    return float(scale) * (1.0 - protected) + protected


def build_16ch_trajectory(mouth_rows: list[dict], neutral_rest: dict[int, float], control_hz: float) -> list[dict]:
    frame_ms = 1000.0 / float(control_hz)
    rows = []
    for mouth_row in mouth_rows:
        frame_id = int(mouth_row["frame_id"])
        values = [float(neutral_rest.get(idx, 0.0)) for idx in range(16)]
        for name, idx in zip(MOUTH_CSV_NAMES, MOUTH_INDICES):
            values[idx] = float(mouth_row[name])

        row = {"frame_id": frame_id, "time_ms": round(frame_id * frame_ms)}
        for name, value in zip(SERVO_NAMES, values):
            row[name] = round(float(value), 6)
        rows.append(row)
    return rows


def handle_silence_frames(
    full_rows: list[dict],
    rms_rows: list[dict],
    neutral_rest: dict[int, float],
    short_hold_ms: int = 120,
    return_frames: int = 4,
    control_hz: float = 25.0,
) -> list[dict]:
    out = [dict(row) for row in full_rows]
    if not out:
        return out

    active = [int(row.get("active", 0)) == 1 for row in rms_rows]
    short_frames = max(1, int(round(short_hold_ms / (1000.0 / control_hz))))
    neutral_mouth = clamp_mouth_array(np.asarray([neutral_rest.get(idx, 0.0) for idx in MOUTH_INDICES], dtype=np.float32))

    start = None
    for i, value in enumerate(active + [True]):
        if not value and start is None:
            start = i
        elif value and start is not None:
            end = i - 1
            length = end - start + 1
            prev = _previous_mouth(out, start, neutral_mouth)
            if length < short_frames:
                for row_idx in range(start, min(end + 1, len(out))):
                    _set_mouth(out[row_idx], prev)
            else:
                transition = min(length, max(1, int(return_frames)))
                for k, row_idx in enumerate(range(start, min(end + 1, len(out)))):
                    if k < transition:
                        alpha = (k + 1) / transition
                        mouth = prev * (1.0 - alpha) + neutral_mouth * alpha
                    else:
                        mouth = neutral_mouth
                    _set_mouth(out[row_idx], mouth)
            start = None
    return out


def _previous_mouth(rows: list[dict], start_idx: int, fallback: np.ndarray) -> np.ndarray:
    if start_idx <= 0:
        return fallback
    row = rows[start_idx - 1]
    return np.asarray([float(row[name]) for name in MOUTH_SERVO_NAMES], dtype=np.float32)


def _set_mouth(row: dict, mouth: np.ndarray):
    for name, value in zip(MOUTH_SERVO_NAMES, clamp_mouth_array(mouth)):
        row[name] = round(float(value), 6)


def clamp_servo_value(name: str, value: float) -> float:
    lo, hi = SERVO_RANGES.get(name, (-1.0, 1.0))
    return max(lo, min(hi, float(value)))


def clamp_mouth_array(values: np.ndarray) -> np.ndarray:
    out = np.asarray(values, dtype=np.float32).copy()
    for i, (lo, hi) in enumerate(MOUTH_VALUE_RANGES):
        out[i] = max(lo, min(hi, float(out[i])))
    return out
