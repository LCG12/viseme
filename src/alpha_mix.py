from __future__ import annotations


def _curve_alpha(alpha: float, curve: str) -> float:
    alpha = max(0.0, min(1.0, float(alpha)))
    if curve == "smootherstep":
        return 3.0 * alpha * alpha - 2.0 * alpha * alpha * alpha
    return alpha


def compute_alpha_mix(
    allocation_rows: list[dict],
    control_hz: float = 25.0,
    curve: str = "linear",
) -> list[dict]:
    rows = []
    frame_ms = 1000.0 / float(control_hz)
    for item in allocation_rows:
        start = int(item["start_frame"])
        end = int(item["end_frame"])
        denom = max(1, end - start)
        for frame_id in range(start, end + 1):
            alpha = 1.0 if start == end else (frame_id - start) / denom
            alpha = _curve_alpha(alpha, curve)
            rows.append(
                {
                    "frame_id": frame_id,
                    "time_ms": round(frame_id * frame_ms),
                    "phrase_idx": int(item["phrase_idx"]),
                    "syllable_idx": int(item["syllable_idx"]),
                    "global_syllable_idx": int(item["global_syllable_idx"]),
                    "syllable": item["syllable"],
                    "start_viseme": int(item["start_viseme"]),
                    "end_viseme": int(item["end_viseme"]),
                    "alpha": round(alpha, 6),
                }
            )
    rows.sort(key=lambda row: int(row["frame_id"]))
    return rows

