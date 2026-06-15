from __future__ import annotations

import unicodedata


def detect_active_segments(rms_rows: list[dict], control_hz: float = 25.0) -> list[dict]:
    frame_ms = 1000.0 / float(control_hz)
    segments = []
    start = None
    for i, row in enumerate(rms_rows + [{"active": 0}]):
        active = int(row.get("active", 0)) == 1
        if active and start is None:
            start = i
        elif not active and start is not None:
            end = i - 1
            segments.append(
                {
                    "segment_idx": len(segments),
                    "start_frame": start,
                    "end_frame": end,
                    "start_time_ms": round(start * frame_ms),
                    "end_time_ms": round(end * frame_ms),
                }
            )
            start = None
    return segments


def align_phrases_to_segments(
    paragraph_id: str,
    phrases: list[dict],
    segments: list[dict],
    n_frames: int,
    control_hz: float = 25.0,
) -> list[dict]:
    if not phrases:
        return []

    frame_ms = 1000.0 / float(control_hz)

    if segments:
        if len(phrases) == len(segments):
            return [
                _phrase_segment_row(paragraph_id, phrase, segment, frame_ms, fallback=0)
                for phrase, segment in zip(phrases, segments)
            ]

        if len(segments) >= len(phrases):
            return _align_many_segments_to_phrases(
                paragraph_id,
                phrases,
                segments,
                frame_ms,
            )

    if segments:
        start = min(int(s["start_frame"]) for s in segments)
        end = max(int(s["end_frame"]) for s in segments)
        return _split_span_to_phrases(
            paragraph_id,
            phrases,
            start,
            end,
            frame_ms,
            segment_idx=int(segments[0]["segment_idx"]),
            fallback=1,
        )
    else:
        start = 0
        end = max(0, int(n_frames) - 1)

    return _split_span_to_phrases(
        paragraph_id,
        phrases,
        start,
        end,
        frame_ms,
        segment_idx=0,
        fallback=1,
    )


def _align_many_segments_to_phrases(
    paragraph_id: str,
    phrases: list[dict],
    segments: list[dict],
    frame_ms: float,
) -> list[dict]:
    weights = [_phrase_weight(phrase) for phrase in phrases]
    total_weight = sum(weights) or float(len(phrases))
    segment_lengths = [
        max(1, int(segment["end_frame"]) - int(segment["start_frame"]) + 1)
        for segment in segments
    ]
    active_prefix = [0]
    for length in segment_lengths:
        active_prefix.append(active_prefix[-1] + length)

    boundaries = []
    prev_k = 0
    used_weight = 0.0
    for phrase_pos in range(len(phrases) - 1):
        used_weight += weights[phrase_pos]
        target = active_prefix[-1] * used_weight / total_weight
        min_k = prev_k + 1
        max_k = len(segments) - (len(phrases) - phrase_pos - 1)
        boundary_k = _best_boundary_index(
            segments,
            active_prefix,
            target,
            min_k,
            max_k,
        )
        boundaries.append(boundary_k)
        prev_k = boundary_k
    boundaries.append(len(segments))

    rows = []
    start_k = 0
    for phrase, end_k in zip(phrases, boundaries):
        first_segment = segments[start_k]
        last_segment = segments[end_k - 1]
        rows.append(
            {
                "paragraph_id": paragraph_id,
                "phrase_idx": int(phrase["phrase_idx"]),
                "segment_idx": int(first_segment["segment_idx"]),
                "start_frame": int(first_segment["start_frame"]),
                "end_frame": int(last_segment["end_frame"]),
                "start_time_ms": round(int(first_segment["start_frame"]) * frame_ms),
                "end_time_ms": round(int(last_segment["end_frame"]) * frame_ms),
                "fallback": 0,
            }
        )
        start_k = end_k
    return rows


def _best_boundary_index(
    segments: list[dict],
    active_prefix: list[int],
    target_active_frame: float,
    min_k: int,
    max_k: int,
) -> int:
    best_k = min_k
    best_score = float("inf")
    for k in range(min_k, max_k + 1):
        gap_frames = _gap_after_segment(segments, k - 1)
        # Prefer real silence boundaries, but keep phrase duration close to text weight.
        score = abs(active_prefix[k] - target_active_frame) - min(gap_frames, 20) * 0.65
        if score < best_score:
            best_score = score
            best_k = k
    return best_k


def _split_span_to_phrases(
    paragraph_id: str,
    phrases: list[dict],
    start_frame: int,
    end_frame: int,
    frame_ms: float,
    segment_idx: int,
    fallback: int,
) -> list[dict]:
    weights = [_phrase_weight(phrase) for phrase in phrases]
    total_weight = sum(weights) or float(len(phrases))
    total_frames = max(1, int(end_frame) - int(start_frame) + 1)
    rows = []
    current_start = int(start_frame)
    used_weight = 0.0

    for phrase_pos, phrase in enumerate(phrases):
        if phrase_pos == len(phrases) - 1:
            current_end = int(end_frame)
        else:
            used_weight += weights[phrase_pos]
            boundary = int(start_frame) + round(total_frames * used_weight / total_weight) - 1
            current_end = max(current_start, min(int(end_frame), boundary))

        rows.append(
            {
                "paragraph_id": paragraph_id,
                "phrase_idx": int(phrase["phrase_idx"]),
                "segment_idx": int(segment_idx),
                "start_frame": int(current_start),
                "end_frame": int(current_end),
                "start_time_ms": round(int(current_start) * frame_ms),
                "end_time_ms": round(int(current_end) * frame_ms),
                "fallback": int(fallback),
            }
        )
        current_start = min(int(end_frame), current_end + 1)

    return rows


def _gap_after_segment(segments: list[dict], segment_idx: int) -> int:
    if segment_idx < 0 or segment_idx >= len(segments) - 1:
        return 0
    return max(
        0,
        int(segments[segment_idx + 1]["start_frame"])
        - int(segments[segment_idx]["end_frame"])
        - 1,
    )


def _phrase_weight(phrase: dict) -> float:
    text = str(phrase.get("text", ""))
    weight = 0.0
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        if category[0] in {"P", "S"}:
            continue
        if ch.isascii() and ch.isalnum():
            weight += 0.75
        elif ch.isalnum():
            weight += 1.0
    return max(1.0, weight)


def _phrase_segment_row(
    paragraph_id: str,
    phrase: dict,
    segment: dict,
    frame_ms: float,
    fallback: int,
) -> dict:
    return {
        "paragraph_id": paragraph_id,
        "phrase_idx": int(phrase["phrase_idx"]),
        "segment_idx": int(segment["segment_idx"]),
        "start_frame": int(segment["start_frame"]),
        "end_frame": int(segment["end_frame"]),
        "start_time_ms": int(
            segment.get("start_time_ms", round(int(segment["start_frame"]) * frame_ms))
        ),
        "end_time_ms": int(
            segment.get("end_time_ms", round(int(segment["end_frame"]) * frame_ms))
        ),
        "fallback": int(fallback),
    }
