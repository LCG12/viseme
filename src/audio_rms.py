from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np


def _pcm_to_float(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (data - 128.0) / 128.0
    if sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        return data / 32768.0
    if sample_width == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        signed = (
            a[:, 0].astype(np.int32)
            | (a[:, 1].astype(np.int32) << 8)
            | (a[:, 2].astype(np.int32) << 16)
        )
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        return signed.astype(np.float32) / 8388608.0
    if sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32)
        return data / 2147483648.0
    raise ValueError(f"Unsupported WAV sample width: {sample_width}")


def read_wav_mono(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())

    audio = _pcm_to_float(raw, sample_width)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio.astype(np.float32), int(sample_rate)


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) == 0:
        return values
    window = max(1, int(window))
    pad = window // 2
    kernel = np.ones(window, dtype=np.float32) / float(window)
    padded = np.pad(values, (pad, window - pad - 1), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def fill_short_gaps(active: np.ndarray, max_gap: int) -> np.ndarray:
    if max_gap <= 0:
        return active
    out = active.copy()
    start = None
    for i, value in enumerate(out):
        if not value and start is None:
            start = i
        elif value and start is not None:
            if i - start <= max_gap and start > 0:
                out[start:i] = True
            start = None
    return out


def remove_short_runs(active: np.ndarray, min_active_frames: int) -> np.ndarray:
    if min_active_frames <= 1:
        return active
    out = active.copy()
    start = None
    for i, value in enumerate(np.r_[out, False]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start < min_active_frames:
                out[start:i] = False
            start = None
    return out


def extract_rms_envelope(
    wav_path: str | Path,
    control_hz: float = 25.0,
    threshold: float = 0.10,
    smooth_window: int = 3,
    min_active_frames: int = 2,
    max_silence_gap_fill: int = 2,
) -> tuple[list[dict], dict]:
    audio, sample_rate = read_wav_mono(wav_path)
    frame_size = max(1, int(round(sample_rate / control_hz)))
    n_frames = max(1, int(math.ceil(len(audio) / frame_size)))

    rms = np.zeros(n_frames, dtype=np.float32)
    for frame_id in range(n_frames):
        start = frame_id * frame_size
        end = min(len(audio), start + frame_size)
        frame = audio[start:end]
        rms[frame_id] = float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0

    max_rms = float(np.max(rms)) if len(rms) else 0.0
    rms_norm = rms / max(max_rms, 1e-8)
    active_score = moving_average(rms_norm, smooth_window)
    active = active_score > float(threshold)
    active = fill_short_gaps(active, int(max_silence_gap_fill))
    active = remove_short_runs(active, int(min_active_frames))

    frame_ms = 1000.0 / float(control_hz)
    rows = []
    for frame_id in range(n_frames):
        rows.append(
            {
                "frame_id": frame_id,
                "time_ms": round(frame_id * frame_ms),
                "rms": round(float(rms[frame_id]), 8),
                "rms_norm": round(float(rms_norm[frame_id]), 6),
                "active": int(bool(active[frame_id])),
            }
        )

    meta = {
        "sample_rate": sample_rate,
        "control_hz": float(control_hz),
        "frame_size_samples": frame_size,
        "frames": n_frames,
        "threshold": float(threshold),
        "smooth_window": int(smooth_window),
        "min_active_frames": int(min_active_frames),
        "max_silence_gap_fill": int(max_silence_gap_fill),
        "duration_seconds": float(len(audio) / sample_rate) if sample_rate else 0.0,
    }
    return rows, meta

