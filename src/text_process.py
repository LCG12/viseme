from __future__ import annotations

import re


PHRASE_PUNCT_RE = re.compile(r"([，,。.!！?？；;：:\n\r]+)")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def split_phrases(text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []

    phrases: list[dict] = []
    current: list[str] = []
    phrase_idx = 0

    for ch in text:
        if PHRASE_PUNCT_RE.fullmatch(ch):
            phrase_text = normalize_text("".join(current))
            if phrase_text:
                phrases.append(
                    {
                        "phrase_idx": phrase_idx,
                        "text": phrase_text,
                        "punctuation": ch,
                    }
                )
                phrase_idx += 1
            current = []
        else:
            current.append(ch)

    phrase_text = normalize_text("".join(current))
    if phrase_text:
        phrases.append(
            {
                "phrase_idx": phrase_idx,
                "text": phrase_text,
                "punctuation": "",
            }
        )

    return phrases


def build_phrase_doc(paragraph_id: str, text: str) -> dict:
    return {
        "paragraph_id": paragraph_id,
        "phrases": split_phrases(text),
    }

