from __future__ import annotations

import json
import math
from pathlib import Path


CLOSURE_INITIALS = {"b", "p", "m"}
HIGH_DOMINANCE_INITIALS = {"b", "p", "m", "f"}
LOW_DOMINANCE_INITIALS = {"d", "t", "n", "l", "zh", "ch", "sh", "r", "z", "c", "s"}
OPEN_FINALS = {"a", "an", "ang", "ia", "ian", "iang", "ua", "uan", "uang"}
ROUND_FINALS = {"o", "ao", "ou", "uo", "ong"}
LONG_FINALS = OPEN_FINALS | ROUND_FINALS | {"e", "en", "eng", "ing", "ai", "ei", "ui"}

# Windows SAPI uses a 22-viseme set. We compress it into this robot's 8
# Mandarin visemes so TTS timing events can drive the same downstream pipeline.
SAPI_VISEME_TO_ROBOT = {
    0: 0,   # silence/rest
    1: 4,   # ae/ax/ah-like mid vowel
    2: 7,   # aa/open vowel
    3: 6,   # ao-like round open vowel
    4: 4,   # ey/eh/uh-like mid vowel
    5: 4,   # er-like vowel
    6: 5,   # iy/ih/y-like wide vowel
    7: 3,   # w/uw-like round narrow vowel
    8: 6,   # ow-like round vowel
    9: 7,   # aw-like open vowel
    10: 6,  # oy-like round vowel
    11: 5,  # ay-like wide vowel
    12: 4,  # h
    13: 2,  # r
    14: 2,  # l
    15: 5,  # s/z
    16: 2,  # sh/ch/j/zh
    17: 2,  # th/dh
    18: 1,  # f/v
    19: 2,  # d/t/n
    20: 4,  # k/g/ng
    21: 0,  # p/b/m
}


def build_estimated_phone_alignment(
    paragraph_id: str,
    syllable_doc: dict,
    phrase_segments: list[dict],
    control_hz: float = 25.0,
) -> list[dict]:
    by_phrase: dict[int, list[dict]] = {}
    for syllable in syllable_doc["syllables"]:
        by_phrase.setdefault(int(syllable["phrase_idx"]), []).append(syllable)

    rows = []
    frame_ms = 1000.0 / float(control_hz)
    source = "estimated"

    for phrase_segment in phrase_segments:
        phrase_idx = int(phrase_segment["phrase_idx"])
        phrase_syllables = (
            syllable_doc["syllables"]
            if phrase_idx == -1
            else by_phrase.get(phrase_idx, [])
        )
        units = _build_phone_units(phrase_syllables)
        spans = _allocate_weighted_spans(
            int(phrase_segment["start_frame"]),
            int(phrase_segment["end_frame"]),
            [unit["duration_weight"] for unit in units],
        )
        for unit, (start_frame, end_frame) in zip(units, spans):
            rows.append(
                {
                    "paragraph_id": paragraph_id,
                    "phrase_idx": int(unit["phrase_idx"]),
                    "syllable_idx": int(unit["syllable_idx"]),
                    "global_syllable_idx": int(unit["global_syllable_idx"]),
                    "syllable": unit["syllable"],
                    "phone_idx": int(unit["phone_idx"]),
                    "phone": unit["phone"],
                    "phone_role": unit["phone_role"],
                    "viseme_id": int(unit["viseme_id"]),
                    "start_frame": int(start_frame),
                    "end_frame": int(end_frame),
                    "start_time_ms": round(int(start_frame) * frame_ms),
                    "end_time_ms": round(int(end_frame) * frame_ms),
                    "duration_weight": round(float(unit["duration_weight"]), 3),
                    "source": source,
                }
            )

    rows.sort(
        key=lambda row: (
            int(row["start_frame"]),
            int(row["global_syllable_idx"]),
            int(row["phone_idx"]),
        )
    )
    return rows


def build_tts_viseme_alignment(
    paragraph_id: str,
    syllable_doc: dict,
    phrase_segments: list[dict],
    tts_events_path: str | Path,
    control_hz: float = 25.0,
    rms_rows: list[dict] | None = None,
) -> list[dict]:
    reference_rows = build_estimated_phone_alignment(
        paragraph_id,
        syllable_doc,
        phrase_segments,
        control_hz=control_hz,
    )
    event_data = json.loads(Path(tts_events_path).read_text(encoding="utf-8-sig"))
    raw_events = event_data.get("events", event_data if isinstance(event_data, list) else [])
    viseme_events = [
        event for event in raw_events
        if str(event.get("type", "")).lower() == "viseme"
    ]
    viseme_events.sort(key=lambda event: float(event.get("audio_position_ms", 0.0)))
    if not reference_rows or not viseme_events:
        return []

    frame_ms = 1000.0 / float(control_hz)
    phone_counts_by_syllable: dict[int, int] = {}
    active_frames = {
        int(row["frame_id"])
        for row in (rms_rows or [])
        if int(row.get("active", 0)) == 1
    }
    rows = []

    for event_idx, event in enumerate(viseme_events):
        raw_viseme = int(event.get("viseme", 0))
        start_ms = max(0.0, float(event.get("audio_position_ms", 0.0)))
        duration_ms = max(frame_ms, float(event.get("duration_ms", frame_ms)))
        end_ms = start_ms + duration_ms

        if event_idx + 1 < len(viseme_events):
            next_start_ms = float(viseme_events[event_idx + 1].get("audio_position_ms", end_ms))
            if next_start_ms > start_ms:
                # Treat SAPI viseme events as state changes: hold the current
                # mouth shape until the next event. This avoids neutral gaps
                # inside speech when SAPI event durations are sparse.
                end_ms = max(start_ms, next_start_ms - 1.0)

        reference = _nearest_reference_row(reference_rows, start_ms)
        global_idx = int(reference["global_syllable_idx"])
        phone_idx = phone_counts_by_syllable.get(global_idx, 0)

        start_frame = max(0, int(round(start_ms / frame_ms)))
        end_frame = max(start_frame, int(math.floor(max(0.0, end_ms - 0.001) / frame_ms)))
        if raw_viseme == 0:
            if _has_active_overlap(start_frame, end_frame, active_frames):
                _append_estimated_fallback_rows(
                    rows,
                    reference_rows,
                    paragraph_id,
                    start_frame,
                    end_frame,
                    frame_ms,
                    phone_counts_by_syllable,
                )
            continue

        phone_counts_by_syllable[global_idx] = phone_idx + 1
        rows.append(
            {
                "paragraph_id": paragraph_id,
                "phrase_idx": int(reference["phrase_idx"]),
                "syllable_idx": int(reference["syllable_idx"]),
                "global_syllable_idx": global_idx,
                "syllable": reference["syllable"],
                "phone_idx": phone_idx,
                "phone": f"sapi_viseme_{raw_viseme}",
                "phone_role": "tts_viseme",
                "viseme_id": int(SAPI_VISEME_TO_ROBOT.get(raw_viseme, 4)),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_time_ms": round(start_frame * frame_ms),
                "end_time_ms": round(end_frame * frame_ms),
                "duration_weight": round(max(1.0, (end_frame - start_frame + 1)), 3),
                "raw_viseme_id": raw_viseme,
                "source": "tts_viseme",
            }
        )

    rows.sort(
        key=lambda row: (
            int(row["start_frame"]),
            int(row["global_syllable_idx"]),
            int(row["phone_idx"]),
        )
    )
    return rows


def _append_estimated_fallback_rows(
    rows: list[dict],
    reference_rows: list[dict],
    paragraph_id: str,
    start_frame: int,
    end_frame: int,
    frame_ms: float,
    phone_counts_by_syllable: dict[int, int],
):
    for reference in reference_rows:
        ref_start = int(reference["start_frame"])
        ref_end = int(reference["end_frame"])
        if ref_end < start_frame or ref_start > end_frame:
            continue

        global_idx = int(reference["global_syllable_idx"])
        phone_idx = phone_counts_by_syllable.get(global_idx, 0)
        phone_counts_by_syllable[global_idx] = phone_idx + 1
        clipped_start = max(start_frame, ref_start)
        clipped_end = min(end_frame, ref_end)
        rows.append(
            {
                "paragraph_id": paragraph_id,
                "phrase_idx": int(reference["phrase_idx"]),
                "syllable_idx": int(reference["syllable_idx"]),
                "global_syllable_idx": global_idx,
                "syllable": reference["syllable"],
                "phone_idx": phone_idx,
                "phone": reference["phone"],
                "phone_role": reference["phone_role"],
                "viseme_id": int(reference["viseme_id"]),
                "start_frame": clipped_start,
                "end_frame": clipped_end,
                "start_time_ms": round(clipped_start * frame_ms),
                "end_time_ms": round(clipped_end * frame_ms),
                "duration_weight": round(max(1.0, clipped_end - clipped_start + 1), 3),
                "raw_viseme_id": 0,
                "source": "tts_viseme_fallback_estimated",
            }
        )


def _build_phone_units(syllables: list[dict]) -> list[dict]:
    units = []
    for syllable in syllables:
        initial = str(syllable.get("initial", ""))
        final = str(syllable.get("final", ""))
        start_v = int(syllable["start_viseme"])
        end_v = int(syllable["end_viseme"])

        phone_parts = []
        if initial:
            phone_parts.append(("initial", initial, start_v))
        if final:
            phone_parts.append(("final", final, end_v))
        if not phone_parts:
            phone_parts.append(("syllable", str(syllable["syllable"]), end_v))

        for phone_idx, (role, phone, viseme_id) in enumerate(phone_parts):
            units.append(
                {
                    "phrase_idx": int(syllable["phrase_idx"]),
                    "syllable_idx": int(syllable["syllable_idx"]),
                    "global_syllable_idx": int(syllable["global_syllable_idx"]),
                    "syllable": syllable["syllable"],
                    "phone_idx": phone_idx,
                    "phone": phone,
                    "phone_role": role,
                    "viseme_id": int(viseme_id),
                    "duration_weight": _duration_weight(phone, role),
                }
            )
    return units


def _duration_weight(phone: str, role: str) -> float:
    if role == "initial" and phone in CLOSURE_INITIALS:
        return 0.78
    if role == "initial" and phone in HIGH_DOMINANCE_INITIALS:
        return 0.86
    if role == "initial" and phone in LOW_DOMINANCE_INITIALS:
        return 0.62
    if role == "initial":
        return 0.68
    if role == "final" and phone in OPEN_FINALS:
        return 2.35
    if role == "final" and phone in ROUND_FINALS:
        return 2.15
    if role == "final" and phone in LONG_FINALS:
        return 2.0
    if role == "final":
        return 1.75
    return 1.0


def _allocate_weighted_spans(
    start_frame: int,
    end_frame: int,
    weights: list[float],
) -> list[tuple[int, int]]:
    if not weights:
        return []

    total_frames = max(1, int(end_frame) - int(start_frame) + 1)
    count = len(weights)
    if total_frames < count:
        frames = [int(start_frame) + min(idx, total_frames - 1) for idx in range(count)]
        return [(frame, frame) for frame in frames]

    total_weight = sum(max(0.001, float(weight)) for weight in weights)
    remaining_frames = total_frames - count
    exact_extra = [
        max(0.001, float(weight)) / total_weight * remaining_frames
        for weight in weights
    ]
    extras = [int(math.floor(value)) for value in exact_extra]
    remainder = remaining_frames - sum(extras)
    order = sorted(range(count), key=lambda idx: exact_extra[idx] - extras[idx], reverse=True)
    for idx in order[:remainder]:
        extras[idx] += 1

    spans = []
    cursor = int(start_frame)
    for extra in extras:
        length = 1 + int(extra)
        span_end = min(int(end_frame), cursor + length - 1)
        spans.append((cursor, span_end))
        cursor = min(int(end_frame), span_end + 1)
    return spans


def _nearest_reference_row(reference_rows: list[dict], time_ms: float) -> dict:
    best_row = reference_rows[0]
    best_distance = float("inf")
    for row in reference_rows:
        start = float(row["start_time_ms"])
        end = float(row["end_time_ms"])
        if start <= time_ms <= end:
            return row
        distance = min(abs(time_ms - start), abs(time_ms - end))
        if distance < best_distance:
            best_distance = distance
            best_row = row
    return best_row


def _has_active_overlap(start_frame: int, end_frame: int, active_frames: set[int]) -> bool:
    if not active_frames:
        return False
    return any(frame in active_frames for frame in range(int(start_frame), int(end_frame) + 1))
