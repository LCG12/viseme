from __future__ import annotations


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
    if phrases and len(phrases) == len(segments):
        return [
            {
                "paragraph_id": paragraph_id,
                "phrase_idx": int(phrase["phrase_idx"]),
                "segment_idx": int(segment["segment_idx"]),
                "start_frame": int(segment["start_frame"]),
                "end_frame": int(segment["end_frame"]),
                "start_time_ms": int(segment["start_time_ms"]),
                "end_time_ms": int(segment["end_time_ms"]),
                "fallback": 0,
            }
            for phrase, segment in zip(phrases, segments)
        ]

    frame_ms = 1000.0 / float(control_hz)
    if segments:
        start = min(int(s["start_frame"]) for s in segments)
        end = max(int(s["end_frame"]) for s in segments)
    else:
        start = 0
        end = max(0, int(n_frames) - 1)

    return [
        {
            "paragraph_id": paragraph_id,
            "phrase_idx": -1,
            "segment_idx": 0,
            "start_frame": start,
            "end_frame": end,
            "start_time_ms": round(start * frame_ms),
            "end_time_ms": round(end * frame_ms),
            "fallback": 1,
        }
    ]

