from __future__ import annotations

from pathlib import Path

from .constants import DEFAULT_PINYIN_TO_VISEME
from .io_utils import read_json


MULTI_INITIALS = ("zh", "ch", "sh")
SINGLE_INITIALS = tuple("bpmfdtnlgkhjqxrzcsyw")


def load_mapping(path: str | Path | None = None) -> dict:
    if path and Path(path).is_file():
        return read_json(path)
    return DEFAULT_PINYIN_TO_VISEME


def split_pinyin(syllable: str) -> tuple[str, str]:
    s = syllable.lower().replace("u:", "v").replace("ü", "v")
    for initial in MULTI_INITIALS:
        if s.startswith(initial):
            return initial, s[len(initial):]
    if s[:1] in SINGLE_INITIALS:
        return s[:1], s[1:]
    return "", s


def final_to_viseme(final: str, mapping: dict, start_viseme: int | None = None) -> int:
    final_map = mapping.get("final", {})
    f = final.lower().replace("u:", "v").replace("ü", "v")
    if f in final_map:
        return int(final_map[f])

    if f.endswith(("iang", "uang", "ang")):
        return 7
    if f.endswith(("ian", "uan", "an")):
        return 7
    if f.endswith(("ia", "ua", "a")):
        return 7
    if f.endswith(("ong", "uo", "ao", "ou", "o")):
        return 6
    if f.endswith(("ing", "eng", "en", "e")):
        return 4
    if f.endswith(("ai", "ei", "ui", "i")):
        return 5
    if f.startswith(("u", "v")):
        return 3
    if "a" in f:
        return 7
    if "o" in f:
        return 6
    if start_viseme is not None:
        return int(start_viseme)
    return 4


def syllable_to_viseme_pair(syllable: str, mapping: dict | None = None) -> dict:
    mapping = mapping or DEFAULT_PINYIN_TO_VISEME
    s = syllable.lower()
    special = mapping.get("syllable_special", {})
    initial, final = split_pinyin(s)

    if s in special:
        start_v, end_v = special[s]
    else:
        initial_map = mapping.get("initial", {})
        start_v = initial_map.get(initial)
        end_v = final_to_viseme(final, mapping, start_v)
        if start_v is None:
            start_v = end_v

    return {
        "syllable": syllable,
        "initial": initial,
        "final": final,
        "start_viseme": int(start_v),
        "end_viseme": int(end_v),
    }


def map_pinyin_to_visemes(paragraph_id: str, pinyin_doc: dict, mapping: dict | None = None) -> dict:
    mapping = mapping or DEFAULT_PINYIN_TO_VISEME
    syllables = []
    global_idx = 0
    for phrase in pinyin_doc["phrases"]:
        for local_idx, syllable in enumerate(phrase["pinyin"]):
            mapped = syllable_to_viseme_pair(syllable, mapping)
            mapped.update(
                {
                    "global_syllable_idx": global_idx,
                    "phrase_idx": int(phrase["phrase_idx"]),
                    "syllable_idx": local_idx,
                }
            )
            syllables.append(mapped)
            global_idx += 1
    return {"paragraph_id": paragraph_id, "syllables": syllables}

