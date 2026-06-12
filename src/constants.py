from __future__ import annotations


SERVO_NAMES = [
    "brow_head_l",
    "brow_head_r",
    "eyelid_open_l",
    "eyelid_open_r",
    "eye_h_attention_l",
    "eye_h_attention_r",
    "eye_v_attention_l",
    "eye_v_attention_r",
    "mouth_open",
    "mouth_up_corner_l",
    "mouth_up_corner_r",
    "mouth_lip_upper_l",
    "mouth_lip_upper_r",
    "mouth_lip_lower",
    "cheek_l",
    "cheek_r",
]

MOUTH_INDICES = [8, 9, 10, 11, 12, 13]
MOUTH_SERVO_NAMES = [SERVO_NAMES[i] for i in MOUTH_INDICES]
MOUTH_CSV_NAMES = [
    "mouth_open",
    "corner_l",
    "corner_r",
    "upper_lip_l",
    "upper_lip_r",
    "lower_lip",
]

SERVO_RANGES = {
    name: ((0.0, 1.0) if name == "mouth_open" else (-1.0, 1.0))
    for name in SERVO_NAMES
}
MOUTH_VALUE_RANGES = [SERVO_RANGES[name] for name in MOUTH_SERVO_NAMES]

DEFAULT_NEUTRAL_REST = {
    0: 0.0,
    1: 0.0,
    2: 0.0,
    3: 0.0,
    4: 0.0,
    5: 0.0,
    6: 0.10,
    7: 0.0,
    8: 0.0,
    9: 0.0,
    10: 0.0,
    11: 0.0,
    12: 0.0,
    13: 0.0,
    14: 0.0,
    15: 0.0,
}

VISEME_TABLE = {
    0: ["b", "p", "m"],
    1: ["f"],
    2: ["d", "t", "n", "l", "zh", "ch", "sh", "r"],
    3: ["w", "u"],
    4: ["e", "en", "eng", "k", "g", "h"],
    5: ["i", "j", "q", "x", "z", "c", "s"],
    6: ["o", "ong"],
    7: ["a", "an", "ang"],
}

SHAPE_LABELS = {
    0: "closed_lip",
    1: "small_labiodental",
    2: "small_open",
    3: "small_round",
    4: "mid_open",
    5: "wide_flat",
    6: "round_open",
    7: "large_open",
}

DEFAULT_VISEME_TARGETS = {
    0: [0.00, -0.06, -0.06, -0.05, -0.05, -0.16],
    1: [0.06, -0.02, -0.02, 0.08, 0.08, 0.24],
    2: [0.10, 0.04, 0.04, 0.02, 0.02, 0.06],
    3: [0.16, -0.20, -0.20, 0.05, 0.05, 0.12],
    4: [0.18, 0.08, 0.08, 0.04, 0.04, 0.10],
    5: [0.16, 0.22, 0.22, 0.04, 0.04, 0.06],
    6: [0.30, -0.16, -0.16, 0.07, 0.07, 0.18],
    7: [0.46, 0.06, 0.06, 0.09, 0.09, 0.24],
}

DEFAULT_PINYIN_TO_VISEME = {
    "initial": {
        "b": 0,
        "p": 0,
        "m": 0,
        "f": 1,
        "d": 2,
        "t": 2,
        "n": 2,
        "l": 2,
        "zh": 2,
        "ch": 2,
        "sh": 2,
        "r": 2,
        "w": 3,
        "g": 4,
        "k": 4,
        "h": 4,
        "j": 5,
        "q": 5,
        "x": 5,
        "z": 5,
        "c": 5,
        "s": 5,
        "y": 5,
    },
    "final": {
        "a": 7,
        "an": 7,
        "ang": 7,
        "ia": 7,
        "ian": 7,
        "iang": 7,
        "ua": 7,
        "uan": 7,
        "uang": 7,
        "o": 6,
        "ao": 6,
        "ou": 6,
        "uo": 6,
        "ong": 6,
        "u": 3,
        "e": 4,
        "en": 4,
        "eng": 4,
        "ing": 4,
        "i": 5,
        "ai": 5,
        "ei": 5,
        "ui": 5,
    },
    "syllable_special": {
        "wu": [3, 3],
        "yi": [5, 5],
        "wo": [3, 6],
        "zi": [5, 5],
        "ci": [5, 5],
        "si": [5, 5],
        "zhi": [2, 5],
        "chi": [2, 5],
        "shi": [2, 5],
        "ri": [2, 5],
    },
}
