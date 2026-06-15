from __future__ import annotations

from .constants import MOUTH_CSV_NAMES, SHAPE_LABELS


SAPI_VISEME_HINTS = {
    0: "silence_rest",
    1: "ae_ax_ah_like",
    2: "aa_open",
    3: "ao_round_open",
    4: "ey_eh_uh_like",
    5: "er_like",
    6: "iy_ih_y_like",
    7: "w_uw_round",
    8: "ow_round",
    9: "aw_open",
    10: "oy_round",
    11: "ay_wide",
    12: "h",
    13: "r",
    14: "l",
    15: "s_z",
    16: "sh_ch_j_zh",
    17: "th_dh",
    18: "f_v",
    19: "d_t_n",
    20: "k_g_ng",
    21: "p_b_m",
}


MAPPING_REPORT_FIELDS = [
    "source",
    "raw_viseme_id",
    "raw_viseme_hint",
    "mapped_viseme_id",
    "shape_label",
    "event_count",
    "frame_count",
    "avg_duration_frames",
    "avg_duration_ms",
    *[f"target_{name}" for name in MOUTH_CSV_NAMES],
    "observed_mouth_open_min",
    "observed_mouth_open_avg",
    "observed_mouth_open_max",
    "sample_syllables",
    "sample_phones",
    "sample_frame_ranges",
    "notes",
]


def build_viseme_mapping_report(
    phone_alignment: list[dict],
    mouth_rows: list[dict],
    viseme_poses: dict,
    control_hz: float,
    sample_limit: int = 8,
) -> list[dict]:
    mouth_by_frame = {
        int(row["frame_id"]): row
        for row in mouth_rows
        if str(row.get("frame_id", "")).strip() != ""
    }
    frame_ms = 1000.0 / float(control_hz)
    groups: dict[tuple[str, int | None, int], dict] = {}

    for alignment in phone_alignment:
        mapped_id = _parse_int(alignment.get("viseme_id"), default=-1)
        raw_id = _parse_optional_int(alignment.get("raw_viseme_id"))
        source = str(alignment.get("source") or "unknown")
        key = (source, raw_id, mapped_id)
        group = groups.setdefault(key, _empty_group(source, raw_id, mapped_id))

        start_frame = _parse_int(alignment.get("start_frame"), default=0)
        end_frame = _parse_int(alignment.get("end_frame"), default=start_frame)
        if end_frame < start_frame:
            start_frame, end_frame = end_frame, start_frame

        frame_count = max(0, end_frame - start_frame + 1)
        group["event_count"] += 1
        group["frame_count"] += frame_count
        _append_sample(group["syllables"], alignment.get("syllable"), sample_limit)
        _append_sample(group["phones"], alignment.get("phone"), sample_limit)
        _append_sample(group["frame_ranges"], f"{start_frame}-{end_frame}", sample_limit)

        for frame_id in range(start_frame, end_frame + 1):
            mouth = mouth_by_frame.get(frame_id)
            if not mouth:
                continue
            value = _parse_float(mouth.get("mouth_open"))
            if value is None:
                continue
            group["observed_count"] += 1
            group["observed_sum"] += value
            group["observed_min"] = value if group["observed_min"] is None else min(group["observed_min"], value)
            group["observed_max"] = value if group["observed_max"] is None else max(group["observed_max"], value)

    rows = []
    for source, raw_id, mapped_id in sorted(groups, key=_sort_key):
        group = groups[(source, raw_id, mapped_id)]
        event_count = max(1, int(group["event_count"]))
        avg_frames = float(group["frame_count"]) / float(event_count)
        row = {
            "source": source,
            "raw_viseme_id": "" if raw_id is None else raw_id,
            "raw_viseme_hint": "" if raw_id is None else SAPI_VISEME_HINTS.get(raw_id, "unknown"),
            "mapped_viseme_id": mapped_id,
            "shape_label": SHAPE_LABELS.get(mapped_id, "unknown"),
            "event_count": group["event_count"],
            "frame_count": group["frame_count"],
            "avg_duration_frames": _round(avg_frames),
            "avg_duration_ms": _round(avg_frames * frame_ms),
            "sample_syllables": ";".join(group["syllables"]),
            "sample_phones": ";".join(group["phones"]),
            "sample_frame_ranges": ";".join(group["frame_ranges"]),
            "notes": _notes(source, raw_id, mapped_id),
        }
        row.update(_target_pose_values(viseme_poses, mapped_id))
        row.update(_observed_values(group))
        rows.append(row)

    return rows


def _empty_group(source: str, raw_id: int | None, mapped_id: int) -> dict:
    return {
        "source": source,
        "raw_id": raw_id,
        "mapped_id": mapped_id,
        "event_count": 0,
        "frame_count": 0,
        "observed_count": 0,
        "observed_sum": 0.0,
        "observed_min": None,
        "observed_max": None,
        "syllables": [],
        "phones": [],
        "frame_ranges": [],
    }


def _target_pose_values(viseme_poses: dict, mapped_id: int) -> dict:
    values = viseme_poses.get(mapped_id)
    out = {}
    for idx, name in enumerate(MOUTH_CSV_NAMES):
        value = ""
        if values is not None and idx < len(values):
            value = _round(float(values[idx]))
        out[f"target_{name}"] = value
    return out


def _observed_values(group: dict) -> dict:
    if int(group["observed_count"]) <= 0:
        return {
            "observed_mouth_open_min": "",
            "observed_mouth_open_avg": "",
            "observed_mouth_open_max": "",
        }
    return {
        "observed_mouth_open_min": _round(group["observed_min"]),
        "observed_mouth_open_avg": _round(group["observed_sum"] / group["observed_count"]),
        "observed_mouth_open_max": _round(group["observed_max"]),
    }


def _notes(source: str, raw_id: int | None, mapped_id: int) -> str:
    if source == "tts_viseme_fallback_estimated":
        return "SAPI raw 0 overlapped active RMS; pinyin-estimated viseme used."
    if source == "tts_viseme" and raw_id == 0 and mapped_id == 0:
        return "SAPI silence/rest."
    if mapped_id in {0, 1}:
        return "Low mouth_open is expected for closure/labiodental shapes."
    return ""


def _append_sample(samples: list[str], value, sample_limit: int):
    text = str(value or "").strip()
    if not text or text in samples or len(samples) >= sample_limit:
        return
    samples.append(text)


def _parse_optional_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return _parse_int(text, default=None)


def _parse_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value) -> float:
    return round(float(value), 6)


def _sort_key(key: tuple[str, int | None, int]):
    source, raw_id, mapped_id = key
    raw_sort = 999 if raw_id is None else raw_id
    return (source, raw_sort, mapped_id)
