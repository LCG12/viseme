from __future__ import annotations

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - handled at runtime for users.
    Style = None
    lazy_pinyin = None


def phrase_to_pinyin(text: str) -> list[str]:
    if lazy_pinyin is None:
        raise RuntimeError("pypinyin is required. Install it with: pip install pypinyin")
    return lazy_pinyin(text, style=Style.NORMAL, errors="ignore")


def phrases_to_pinyin(paragraph_id: str, phrase_doc: dict) -> dict:
    out = {"paragraph_id": paragraph_id, "phrases": []}
    for phrase in phrase_doc["phrases"]:
        out["phrases"].append(
            {
                "phrase_idx": phrase["phrase_idx"],
                "text": phrase["text"],
                "pinyin": phrase_to_pinyin(phrase["text"]),
            }
        )
    return out

