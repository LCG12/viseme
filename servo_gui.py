#!/usr/bin/env python
"""Viseme servo calibration GUI — single-file, self-contained.

Dependencies: flask, numpy, pyserial (optional, for hardware)
Start:   python servo_gui.py --port 5050
"""

from __future__ import annotations

import argparse
import csv
import json
import threading
import time
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request

try:
    import serial
except ImportError:
    serial = None

ROOT = Path(__file__).resolve().parent

# ── 16 servo definitions ──────────────────────────────────────────────
ALL_SERVOS = [
    {"index": 0,  "key": "brow_head_l",       "label": "左眉头",   "short": "BrowL",   "group": "eyebrow"},
    {"index": 1,  "key": "brow_head_r",       "label": "右眉头",   "short": "BrowR",   "group": "eyebrow"},
    {"index": 2,  "key": "eyelid_open_l",     "label": "左眼皮",   "short": "LidL",    "group": "eyelid"},
    {"index": 3,  "key": "eyelid_open_r",     "label": "右眼皮",   "short": "LidR",    "group": "eyelid"},
    {"index": 4,  "key": "eye_h_attention_l", "label": "左眼水平", "short": "EyeHL",   "group": "eye"},
    {"index": 5,  "key": "eye_h_attention_r", "label": "右眼水平", "short": "EyeHR",   "group": "eye"},
    {"index": 6,  "key": "eye_v_attention_l", "label": "左眼垂直", "short": "EyeVL",   "group": "eye"},
    {"index": 7,  "key": "eye_v_attention_r", "label": "右眼垂直", "short": "EyeVR",   "group": "eye"},
    {"index": 8,  "key": "mouth_open",        "label": "张嘴",     "short": "Open",    "group": "mouth"},
    {"index": 9,  "key": "mouth_up_corner_l", "label": "左嘴角",   "short": "CrnL",    "group": "mouth"},
    {"index": 10, "key": "mouth_up_corner_r", "label": "右嘴角",   "short": "CrnR",    "group": "mouth"},
    {"index": 11, "key": "mouth_lip_upper_l", "label": "左上唇",   "short": "UpLipL",  "group": "mouth"},
    {"index": 12, "key": "mouth_lip_upper_r", "label": "右上唇",   "short": "UpLipR",  "group": "mouth"},
    {"index": 13, "key": "mouth_lip_lower",   "label": "下唇",     "short": "LoLip",   "group": "mouth"},
    {"index": 14, "key": "cheek_l",           "label": "左脸颊",   "short": "CheekL",  "group": "cheek"},
    {"index": 15, "key": "cheek_r",           "label": "右脸颊",   "short": "CheekR",  "group": "cheek"},
]

SERVO_GROUPS = [
    {"id": "mouth",   "label": "嘴部", "indices": [8, 9, 10, 11, 12, 13]},
    {"id": "eyebrow", "label": "眉毛", "indices": [0, 1]},
    {"id": "eyelid",  "label": "眼皮", "indices": [2, 3]},
    {"id": "eye",     "label": "眼球", "indices": [4, 5, 6, 7]},
    {"id": "cheek",   "label": "脸颊", "indices": [14, 15]},
]

MOUTH_INDICES = [8, 9, 10, 11, 12, 13]
NON_MOUTH = [0, 1, 2, 3, 4, 5, 6, 7, 14, 15]

MOUTH_NAMES = [
    "mouth_open", "corner_l", "corner_r",
    "upper_lip_l", "upper_lip_r", "lower_lip",
]
MOUTH_RANGES = [
    (0.0, 1.0),
    (-1.0, 1.0),
    (-1.0, 1.0),
    (-1.0, 1.0),
    (-1.0, 1.0),
    (-1.0, 1.0),
]
SERVO_RANGES = {
    servo["index"]: ((0.0, 1.0) if servo["key"] == "mouth_open" else (-1.0, 1.0))
    for servo in ALL_SERVOS
}

CHANNELS = [
    {"key": "mouth_open",  "label": "张嘴",   "short_label": "Open",   "hint": "mouth_open",        "index": 0},
    {"key": "corner_l",    "label": "左嘴角", "short_label": "L Crn",  "hint": "mouth_up_corner_l", "index": 1},
    {"key": "corner_r",    "label": "右嘴角", "short_label": "R Crn",  "hint": "mouth_up_corner_r", "index": 2},
    {"key": "upper_lip_l", "label": "左上唇", "short_label": "L UpL",  "hint": "mouth_lip_upper_l", "index": 3},
    {"key": "upper_lip_r", "label": "右上唇", "short_label": "R UpL",  "hint": "mouth_lip_upper_r", "index": 4},
    {"key": "lower_lip",   "label": "下唇",   "short_label": "Lower",  "hint": "mouth_lip_lower",   "index": 5},
]

# 8-viseme table (from ICCRE 2025 paper)
VISEME_TABLE = {
    0: ["p", "b", "m"],
    1: ["f"],
    2: ["d", "t", "n", "l", "zh", "ch", "sh", "r"],
    3: ["w", "u"],
    4: ["e", "en", "eng", "k", "g", "h"],
    5: ["i", "j", "q", "x", "z", "c", "s"],
    6: ["o", "ong"],
    7: ["a", "an", "ang"],
}

# default viseme target poses. mouth_open is [0,1]; other mouth servos are [-1,1].
VISEME_TARGETS = {
    0: [ 0.00, -0.06, -0.06, -0.05, -0.05, -0.16],
    1: [ 0.06, -0.02, -0.02,  0.08,  0.08,  0.24],
    2: [ 0.10,  0.04,  0.04,  0.02,  0.02,  0.06],
    3: [ 0.16, -0.20, -0.20,  0.05,  0.05,  0.12],
    4: [ 0.18,  0.08,  0.08,  0.04,  0.04,  0.10],
    5: [ 0.16,  0.22,  0.22,  0.04,  0.04,  0.06],
    6: [ 0.30, -0.16, -0.16,  0.07,  0.07,  0.18],
    7: [ 0.46,  0.06,  0.06,  0.09,  0.09,  0.24],
}

VISEME_META = {
    0: {"phonemes": "b,p,m",               "aperture": 0, "shape_label": "closed_lip"},
    1: {"phonemes": "f",                    "aperture": 1, "shape_label": "small_labiodental"},
    2: {"phonemes": "d,t,n,l,zh,ch,sh,r",  "aperture": 1, "shape_label": "small_open"},
    3: {"phonemes": "w,u",                  "aperture": 1, "shape_label": "small_round"},
    4: {"phonemes": "e,en,eng,k,g,h",       "aperture": 3, "shape_label": "mid_open"},
    5: {"phonemes": "i,j,q,x,z,c,s",        "aperture": 2, "shape_label": "wide_flat"},
    6: {"phonemes": "o,ong",                "aperture": 4, "shape_label": "round_open"},
    7: {"phonemes": "a,an,ang",             "aperture": 5, "shape_label": "large_open"},
}

DEFAULT_BASE_CMD = np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.10, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    dtype=np.float32,
)

TERMINATOR = b"\n"
POSE_FILE_DEFAULT = ROOT / "viseme_poses_6d.json"


# ── helpers ────────────────────────────────────────────────────────────
def _fmt_16(vals) -> str:
    return "[" + ",".join(f"{float(v):.2f}" for v in vals) + "]"


def _build_full(mouth_6, neutral_rest: dict) -> np.ndarray:
    cmd = np.zeros(16, dtype=np.float32)
    for i in NON_MOUTH:
        cmd[i] = _clamp_servo(i, neutral_rest.get(i, 0.0))
    mouth = _clamp_mouth(mouth_6)
    for j, mi in enumerate(MOUTH_INDICES):
        cmd[mi] = float(mouth[j])
    return cmd


def _err(msg, status=400):
    r = jsonify({"ok": False, "error": str(msg)})
    r.status_code = status
    return r


def _clamp_servo(index: int, value) -> float:
    lo, hi = SERVO_RANGES.get(int(index), (-1.0, 1.0))
    return max(lo, min(hi, float(value)))


def _clamp_mouth(values) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    if arr.shape != (6,):
        raise ValueError(f"Expected 6 mouth values, got {arr.shape}")
    out = arr.copy()
    for i, (lo, hi) in enumerate(MOUTH_RANGES):
        out[i] = _clamp_servo(MOUTH_INDICES[i], out[i])
    return out


# ── state ──────────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.ser = None
        self.dry = True
        self.port = "COM8"
        self.baud = 115200
        self.last_packet = ""
        self.last_sent_viseme = None

        # 8 viseme mouth poses (dict of list)
        self.poses = {
            i: [round(float(v), 6) for v in _clamp_mouth(VISEME_TARGETS[i])]
            for i in range(8)
        }
        # neutral rest: non-mouth servos
        self.neutral_rest = {
            int(i): float(DEFAULT_BASE_CMD[i]) for i in NON_MOUTH
        }

        self._load_poses()

    @property
    def connected(self) -> bool:
        return self.ser is not None and getattr(self.ser, "is_open", False)

    # ── persistence ────────────────────────────────────────────────
    def _load_poses(self):
        self._load_neutral_from_json(ROOT / "neutral_rest.json")
        self._load_neutral_from_csv(ROOT / "config" / "neutral_rest.csv")

        path = POSE_FILE_DEFAULT
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text("utf-8"))
            raw = data.get("viseme_targets", data)
            for i in range(8):
                k = str(i)
                if k in raw:
                    self.poses[i] = [float(v) for v in _clamp_mouth(raw[k])]
            # also try to load neutral_rest
            nr = data.get("neutral_rest")
            if nr:
                for k, v in nr.items():
                    idx = int(k)
                    if idx in NON_MOUTH:
                        self.neutral_rest[idx] = _clamp_servo(idx, v)
        except Exception:
            pass

    def _load_neutral_from_json(self, path: Path):
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text("utf-8"))
            raw = data.get("neutral_rest", data)
            for k, v in raw.items():
                idx = int(k)
                if idx in NON_MOUTH:
                    self.neutral_rest[idx] = _clamp_servo(idx, v)
        except Exception:
            pass

    def _load_neutral_from_csv(self, path: Path):
        if not path.is_file():
            return
        try:
            with path.open("r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    idx = int(row["servo_id"])
                    if idx in NON_MOUTH:
                        self.neutral_rest[idx] = _clamp_servo(idx, row["value"])
        except Exception:
            pass

    def save_poses(self):
        path = POSE_FILE_DEFAULT
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "space": "mouth_open [0,1], other channels [-1,1]",
            "mouth_names": MOUTH_NAMES,
            "mouth_indices": MOUTH_INDICES,
            "viseme_table": {str(i): v for i, v in VISEME_TABLE.items()},
            "viseme_targets": {
                str(i): [round(float(v), 6) for v in self.poses[i]]
                for i in range(8)
            },
            "neutral_rest": {
                str(i): round(float(self.neutral_rest[i]), 6)
                for i in NON_MOUTH
            },
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        return str(path.resolve())

    # ── serial ─────────────────────────────────────────────────────
    def connect(self, port=None, baud=None, dry=None):
        with self.lock:
            if port:
                self.port = str(port)
            if baud is not None:
                self.baud = int(baud)
            if dry is not None:
                self.dry = bool(dry)
            self.disconnect(send_neutral=False)
            self.last_packet = ""
            if self.dry:
                return
            if serial is None:
                raise RuntimeError("pyserial required. Install it or use dry-run.")
            self.ser = serial.Serial(
                port=self.port, baudrate=self.baud,
                timeout=0.1, stopbits=serial.STOPBITS_ONE,
            )
            time.sleep(0.5)

    def disconnect(self, send_neutral=True):
        with self.lock:
            if self.ser and self.connected:
                try:
                    if send_neutral:
                        self._write(_fmt_16(_build_full(
                            np.zeros(6, dtype=np.float32), self.neutral_rest)))
                finally:
                    self.ser.close()
            self.ser = None

    def _write(self, text: str):
        self.last_packet = text
        if self.dry:
            return
        if not self.connected:
            raise RuntimeError("Serial not connected.")
        self.ser.write(text.encode() + TERMINATOR)
        self.ser.flush()

    def send_pose(self, viseme_id=None, values=None):
        with self.lock:
            if values is not None:
                mouth = _clamp_mouth(values)
                if viseme_id is not None:
                    self.poses[int(viseme_id)] = [float(v) for v in mouth]
            elif viseme_id is not None:
                mouth = _clamp_mouth(self.poses[int(viseme_id)])
            else:
                raise ValueError("need viseme_id or values")
            self._write(_fmt_16(_build_full(mouth, self.neutral_rest)))
            self.last_sent_viseme = int(viseme_id) if viseme_id is not None else None

    # ── snapshot ───────────────────────────────────────────────────
    def snapshot(self):
        with self.lock:
            return {
                "ok": True,
                "pose_file": str(POSE_FILE_DEFAULT),
                "mouth_names": MOUTH_NAMES,
                "mouth_indices": MOUTH_INDICES,
                "base_command": [round(float(v), 4) for v in
                                 _build_full(np.zeros(6), self.neutral_rest)],
                "channels": CHANNELS,
                "viseme_table": {str(k): VISEME_TABLE[k] for k in range(8)},
                "viseme_meta": {
                    str(k): {
                        **VISEME_META[k],
                        "aperture": round(max(0.0, min(1.0, float(self.poses[k][0]))), 4),
                    } for k in range(8)
                },
                "default_targets": {
                    str(k): [round(float(v), 6) for v in _clamp_mouth(VISEME_TARGETS[k])]
                    for k in range(8)
                },
                "poses": {
                    str(k): [round(float(v), 6) for v in _clamp_mouth(self.poses[k])]
                    for k in range(8)
                },
                "all_servos": ALL_SERVOS,
                "servo_groups": SERVO_GROUPS,
                "neutral_rest": {
                    str(i): round(float(self.neutral_rest[i]), 4)
                    for i in NON_MOUTH
                },
                "serial": {
                    "connected": self.connected,
                    "dry_run": self.dry,
                    "port": self.port,
                    "baudrate": self.baud,
                    "last_packet": self.last_packet,
                    "last_sent_viseme": self.last_sent_viseme,
                },
            }


# ── Flask app ─────────────────────────────────────────────────────────
def create_app(state: State) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    # ── state ─────────────────────────────────────────────────────
    @app.get("/api/state")
    def api_state():
        return jsonify(state.snapshot())

    # ── connect / disconnect ───────────────────────────────────────
    @app.post("/api/connect")
    def api_connect():
        d = request.get_json(silent=True) or {}
        try:
            state.connect(
                port=d.get("port"), baud=d.get("baudrate"),
                dry=d.get("dry_run"),
            )
            return jsonify(state.snapshot())
        except Exception as e:
            return _err(e)

    @app.post("/api/disconnect")
    def api_disconnect():
        d = request.get_json(silent=True) or {}
        try:
            state.disconnect(send_neutral=bool(d.get("send_neutral", True)))
            return jsonify(state.snapshot())
        except Exception as e:
            return _err(e)

    # ── viseme poses ──────────────────────────────────────────────
    @app.put("/api/pose/<int:vid>")
    def api_set_pose(vid):
        d = request.get_json(silent=True) or {}
        try:
            values = d.get("values", [])
            state.poses[vid] = [float(v) for v in _clamp_mouth(values[:6])]
            return jsonify(state.snapshot())
        except Exception as e:
            return _err(e)

    @app.post("/api/pose/<int:vid>/zero")
    def api_zero(vid):
        state.poses[vid] = [0.0] * 6
        return jsonify(state.snapshot())

    @app.post("/api/pose/<int:vid>/default")
    def api_default(vid):
        state.poses[vid] = [float(v) for v in _clamp_mouth(VISEME_TARGETS[vid])]
        return jsonify(state.snapshot())

    @app.post("/api/pose/<int:vid>/copy")
    def api_copy(vid):
        d = request.get_json(silent=True) or {}
        src = int(d.get("source_id", 0))
        state.poses[vid] = [float(v) for v in _clamp_mouth(state.poses[src])]
        return jsonify(state.snapshot())

    # ── neutral rest ──────────────────────────────────────────────
    @app.get("/api/neutral-rest")
    def api_get_nr():
        return jsonify({
            str(i): round(float(state.neutral_rest[i]), 4)
            for i in NON_MOUTH
        })

    @app.put("/api/neutral-rest")
    def api_set_nr():
        d = request.get_json(silent=True) or {}
        vals = d.get("values", {})
        with state.lock:
            for k, v in vals.items():
                idx = int(k)
                if idx in NON_MOUTH:
                    state.neutral_rest[idx] = _clamp_servo(idx, v)
        return jsonify(state.snapshot())

    # ── send ──────────────────────────────────────────────────────
    @app.post("/api/send")
    def api_send():
        d = request.get_json(silent=True) or {}
        try:
            state.send_pose(
                viseme_id=d.get("viseme_id"),
                values=d.get("values"),
            )
            return jsonify(state.snapshot())
        except Exception as e:
            return _err(e)

    # ── save / reload / export ────────────────────────────────────
    @app.post("/api/save")
    def api_save():
        try:
            p = state.save_poses()
            return jsonify(state.snapshot())
        except Exception as e:
            return _err(e)

    @app.post("/api/reload")
    def api_reload():
        state._load_poses()
        return jsonify(state.snapshot())

    @app.post("/api/export-csv")
    def api_export():
        d = request.get_json(silent=True) or {}
        base = Path(d.get("out_dir")) if d.get("out_dir") else ROOT / "config"
        base.mkdir(parents=True, exist_ok=True)

        # viseme poses
        pcsv = base / "neutral_viseme_pose_final.csv"
        with pcsv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["viseme_id", *MOUTH_NAMES])
            for i in range(8):
                w.writerow([i, *[round(float(v), 6) for v in _clamp_mouth(state.poses[i])]])

        # viseme meta
        mcsv = base / "viseme_meta.csv"
        with mcsv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["viseme_id", "phonemes", "aperture", "shape_label"])
            for i in range(8):
                m = VISEME_META[i]
                aperture = round(max(0.0, min(1.0, float(state.poses[i][0]))), 4)
                w.writerow([i, m["phonemes"], aperture, m["shape_label"]])

        # neutral rest
        nrcsv = base / "neutral_rest.csv"
        with nrcsv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["servo_id", "servo_name", "value"])
            for s in ALL_SERVOS:
                idx = s["index"]
                if idx in MOUTH_INDICES:
                    value = 0.0
                else:
                    value = state.neutral_rest[idx]
                w.writerow([idx, s["key"], round(float(value), 4)])

        limits_csv = base / "servo_limits.csv"
        with limits_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["servo_name", "min", "max"])
            for s in ALL_SERVOS:
                lo, hi = SERVO_RANGES[s["index"]]
                w.writerow([s["key"], lo, hi])

        return jsonify(state.snapshot())

    return app


# ── CLI ───────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Viseme servo calibration GUI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5050, help="HTTP port")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    state = State()
    app = create_app(state)

    print(f"\n  Viseme Servo GUI")
    print(f"  Open  http://{args.host}:{args.port}")
    print(f"  Pose file: {POSE_FILE_DEFAULT.resolve()}")
    print(f"  Connect serial or enable dry-run from the UI.\n")

    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
