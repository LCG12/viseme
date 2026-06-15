from __future__ import annotations

from collections import defaultdict


CLOSURE_INITIALS = {"b", "p", "m"}
HIGH_DOMINANCE_INITIALS = {"b", "p", "m", "f"}
LOW_DOMINANCE_INITIALS = {"d", "t", "n", "l", "zh", "ch", "sh", "r", "z", "c", "s"}
VOWEL_LIKE_FINALS = {
    "a",
    "an",
    "ang",
    "ia",
    "ian",
    "iang",
    "ua",
    "uan",
    "uang",
    "o",
    "ao",
    "ou",
    "uo",
    "ong",
    "u",
    "e",
    "en",
    "eng",
    "ing",
    "i",
    "ai",
    "ei",
    "ui",
}


def build_phone_events(
    paragraph_id: str,
    allocation_rows: list[dict],
    syllable_doc: dict,
    control_hz: float = 25.0,
) -> list[dict]:
    syllable_by_idx = {
        int(item["global_syllable_idx"]): item
        for item in syllable_doc["syllables"]
    }
    frame_ms = 1000.0 / float(control_hz)
    events = []

    for row in allocation_rows:
        global_idx = int(row["global_syllable_idx"])
        syllable = syllable_by_idx[global_idx]
        initial = str(syllable.get("initial", ""))
        final = str(syllable.get("final", ""))
        start_frame = int(row["start_frame"])
        end_frame = int(row["end_frame"])
        total_frames = max(1, end_frame - start_frame + 1)
        start_v = int(row["start_viseme"])
        end_v = int(row["end_viseme"])

        if initial and final and total_frames >= 3 and start_v != end_v:
            initial_frames = _initial_frame_count(initial, total_frames)
            initial_end = min(end_frame, start_frame + initial_frames - 1)
            final_start = min(end_frame, initial_end + 1)

            events.append(
                _event_row(
                    paragraph_id,
                    row,
                    phone=initial,
                    phone_role="initial",
                    viseme_id=start_v,
                    start_frame=start_frame,
                    end_frame=initial_end,
                    frame_ms=frame_ms,
                    dominance=_dominance(initial, "initial"),
                    motion_profile=_motion_profile(initial, "initial"),
                )
            )
            events.append(
                _event_row(
                    paragraph_id,
                    row,
                    phone=final,
                    phone_role="final",
                    viseme_id=end_v,
                    start_frame=final_start,
                    end_frame=end_frame,
                    frame_ms=frame_ms,
                    dominance=_dominance(final, "final"),
                    motion_profile=_motion_profile(final, "final"),
                )
            )
        else:
            phone = final or initial or str(row["syllable"])
            role = "final" if final else ("initial" if initial else "syllable")
            events.append(
                _event_row(
                    paragraph_id,
                    row,
                    phone=phone,
                    phone_role=role,
                    viseme_id=end_v,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    frame_ms=frame_ms,
                    dominance=_dominance(phone, role),
                    motion_profile=_motion_profile(phone, role),
                )
            )

    return events


def compute_phone_event_mix(
    phone_events: list[dict],
    control_hz: float = 25.0,
    curve: str = "smootherstep",
) -> list[dict]:
    by_syllable: dict[int, list[dict]] = defaultdict(list)
    for event in phone_events:
        by_syllable[int(event["global_syllable_idx"])].append(event)

    rows = []
    frame_ms = 1000.0 / float(control_hz)
    for _, events in sorted(by_syllable.items()):
        events.sort(key=lambda item: int(item["start_frame"]))
        if len(events) == 1:
            event = events[0]
            for frame_id in range(int(event["start_frame"]), int(event["end_frame"]) + 1):
                rows.append(_mix_row(event, frame_id, round(frame_id * frame_ms), event["viseme_id"], event["viseme_id"], 1.0))
            continue

        prev_event = events[0]
        next_event = events[1]
        release_frames = list(range(int(next_event["start_frame"]), int(next_event["end_frame"]) + 1))
        release_len = max(1, len(release_frames))

        for frame_id in range(int(prev_event["start_frame"]), int(prev_event["end_frame"]) + 1):
            rows.append(
                _mix_row(
                    prev_event,
                    frame_id,
                    round(frame_id * frame_ms),
                    int(prev_event["viseme_id"]),
                    int(prev_event["viseme_id"]),
                    1.0,
                )
            )

        for local_idx, frame_id in enumerate(release_frames):
            alpha = 1.0 if release_len == 1 else local_idx / (release_len - 1)
            alpha = _profile_alpha(alpha, str(prev_event["motion_profile"]), str(next_event["motion_profile"]), curve)
            rows.append(
                _mix_row(
                    next_event,
                    frame_id,
                    round(frame_id * frame_ms),
                    int(prev_event["viseme_id"]),
                    int(next_event["viseme_id"]),
                    alpha,
                )
            )

    rows.sort(key=lambda row: int(row["frame_id"]))
    return rows


def _initial_frame_count(initial: str, total_frames: int) -> int:
    if initial in CLOSURE_INITIALS:
        ratio = 0.36
    elif initial in HIGH_DOMINANCE_INITIALS:
        ratio = 0.30
    elif initial in LOW_DOMINANCE_INITIALS:
        ratio = 0.22
    else:
        ratio = 0.24
    return max(1, min(total_frames - 1, int(round(total_frames * ratio))))


def _dominance(phone: str, role: str) -> float:
    if role == "initial" and phone in HIGH_DOMINANCE_INITIALS:
        return 1.0
    if role == "initial" and phone in LOW_DOMINANCE_INITIALS:
        return 0.62
    if role == "final" and phone in VOWEL_LIKE_FINALS:
        return 0.82
    return 0.72


def _motion_profile(phone: str, role: str) -> str:
    if role == "initial" and phone in CLOSURE_INITIALS:
        return "closure"
    if role == "initial" and phone == "f":
        return "labiodental"
    if role == "final":
        return "vowel_hold"
    return "soft_consonant"


def _event_row(
    paragraph_id: str,
    allocation_row: dict,
    phone: str,
    phone_role: str,
    viseme_id: int,
    start_frame: int,
    end_frame: int,
    frame_ms: float,
    dominance: float,
    motion_profile: str,
) -> dict:
    return {
        "paragraph_id": paragraph_id,
        "phrase_idx": int(allocation_row["phrase_idx"]),
        "syllable_idx": int(allocation_row["syllable_idx"]),
        "global_syllable_idx": int(allocation_row["global_syllable_idx"]),
        "syllable": allocation_row["syllable"],
        "phone": phone,
        "phone_role": phone_role,
        "viseme_id": int(viseme_id),
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "start_time_ms": round(int(start_frame) * frame_ms),
        "end_time_ms": round(int(end_frame) * frame_ms),
        "dominance": round(float(dominance), 3),
        "motion_profile": motion_profile,
    }


def _mix_row(event: dict, frame_id: int, time_ms: int, start_v: int, end_v: int, alpha: float) -> dict:
    return {
        "frame_id": int(frame_id),
        "time_ms": int(time_ms),
        "phrase_idx": int(event["phrase_idx"]),
        "syllable_idx": int(event["syllable_idx"]),
        "global_syllable_idx": int(event["global_syllable_idx"]),
        "syllable": event["syllable"],
        "start_viseme": int(start_v),
        "end_viseme": int(end_v),
        "alpha": round(float(alpha), 6),
    }


def _profile_alpha(alpha: float, prev_profile: str, next_profile: str, curve: str) -> float:
    alpha = max(0.0, min(1.0, float(alpha)))
    if prev_profile == "closure":
        # Hold closure briefly, then release quickly into the vowel.
        if alpha < 0.28:
            return 0.0
        alpha = (alpha - 0.28) / 0.72
    elif next_profile == "vowel_hold":
        # Enter the vowel early, then spend more frames near the vowel shape.
        alpha = min(1.0, alpha / 0.72)

    return _curve(alpha, curve)


def _curve(alpha: float, curve: str) -> float:
    alpha = max(0.0, min(1.0, float(alpha)))
    if curve == "smootherstep":
        return 6.0 * alpha**5 - 15.0 * alpha**4 + 10.0 * alpha**3
    if curve == "smoothstep":
        return 3.0 * alpha**2 - 2.0 * alpha**3
    return alpha

