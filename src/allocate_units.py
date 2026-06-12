from __future__ import annotations

import numpy as np


def _allocate_range(start_frame: int, end_frame: int, count: int) -> list[tuple[int, int]]:
    if count <= 0:
        return []
    frames = np.arange(int(start_frame), int(end_frame) + 1)
    if len(frames) == 0:
        frames = np.array([int(start_frame)])
    chunks = np.array_split(frames, count)
    spans = []
    for idx, chunk in enumerate(chunks):
        if len(chunk):
            spans.append((int(chunk[0]), int(chunk[-1])))
        else:
            frame = int(frames[min(idx, len(frames) - 1)])
            spans.append((frame, frame))
    return spans


def allocate_syllable_frames(
    paragraph_id: str,
    syllable_doc: dict,
    phrase_segments: list[dict],
) -> list[dict]:
    syllables = syllable_doc["syllables"]
    rows = []

    if len(phrase_segments) == 1 and int(phrase_segments[0].get("phrase_idx", -1)) == -1:
        segment = phrase_segments[0]
        spans = _allocate_range(segment["start_frame"], segment["end_frame"], len(syllables))
        for syllable, (start, end) in zip(syllables, spans):
            rows.append(_allocation_row(paragraph_id, syllable, start, end))
        return rows

    by_phrase: dict[int, list[dict]] = {}
    for syllable in syllables:
        by_phrase.setdefault(int(syllable["phrase_idx"]), []).append(syllable)

    for segment in phrase_segments:
        phrase_idx = int(segment["phrase_idx"])
        phrase_syllables = by_phrase.get(phrase_idx, [])
        spans = _allocate_range(segment["start_frame"], segment["end_frame"], len(phrase_syllables))
        for syllable, (start, end) in zip(phrase_syllables, spans):
            rows.append(_allocation_row(paragraph_id, syllable, start, end))

    rows.sort(key=lambda row: int(row["global_syllable_idx"]))
    return rows


def _allocation_row(paragraph_id: str, syllable: dict, start: int, end: int) -> dict:
    return {
        "paragraph_id": paragraph_id,
        "phrase_idx": int(syllable["phrase_idx"]),
        "syllable_idx": int(syllable["syllable_idx"]),
        "global_syllable_idx": int(syllable["global_syllable_idx"]),
        "syllable": syllable["syllable"],
        "start_viseme": int(syllable["start_viseme"]),
        "end_viseme": int(syllable["end_viseme"]),
        "start_frame": int(start),
        "end_frame": int(end),
        "num_frames": int(end - start + 1),
    }

