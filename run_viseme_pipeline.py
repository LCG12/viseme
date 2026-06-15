#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.allocate_units import allocate_syllable_frames
from src.alpha_mix import compute_alpha_mix
from src.audio_rms import extract_rms_envelope
from src.config_bootstrap import ensure_default_configs
from src.constants import MOUTH_CSV_NAMES, MOUTH_SERVO_NAMES, SERVO_NAMES
from src.evaluation import ensure_evaluation_templates
from src.io_utils import ensure_dir, read_csv, write_csv, write_json
from src.pinyin_convert import phrases_to_pinyin
from src.phone_alignment import build_estimated_phone_alignment, build_tts_viseme_alignment
from src.phone_events import build_phone_events_from_alignment, compute_phone_event_mix
from src.robot_player import play_audio_and_send_servos
from src.segment_detect import align_phrases_to_segments, detect_active_segments
from src.servo_smoothing import clamp_servo_values, load_servo_limits, smooth_trajectory
from src.servo_trajectory import (
    build_16ch_trajectory,
    generate_mouth_trajectory,
    handle_silence_frames,
    load_neutral_rest,
    load_viseme_poses,
    neutral_mouth_from_rest,
)
from src.text_process import build_phrase_doc
from src.viseme_mapping_report import MAPPING_REPORT_FIELDS, build_viseme_mapping_report
from src.viseme_mapper import load_mapping, map_pinyin_to_visemes


ROOT = Path(__file__).resolve().parent


RMS_FIELDS = ["frame_id", "time_ms", "rms", "rms_norm", "active"]
SEGMENT_FIELDS = ["segment_idx", "start_frame", "end_frame", "start_time_ms", "end_time_ms"]
PHRASE_SEGMENT_FIELDS = [
    "paragraph_id",
    "phrase_idx",
    "segment_idx",
    "start_frame",
    "end_frame",
    "start_time_ms",
    "end_time_ms",
    "fallback",
]
ALLOCATION_FIELDS = [
    "paragraph_id",
    "phrase_idx",
    "syllable_idx",
    "global_syllable_idx",
    "syllable",
    "start_viseme",
    "end_viseme",
    "start_frame",
    "end_frame",
    "num_frames",
]
PHONE_ALIGNMENT_FIELDS = [
    "paragraph_id",
    "phrase_idx",
    "syllable_idx",
    "global_syllable_idx",
    "syllable",
    "phone_idx",
    "phone",
    "phone_role",
    "viseme_id",
    "start_frame",
    "end_frame",
    "start_time_ms",
    "end_time_ms",
    "duration_weight",
    "raw_viseme_id",
    "source",
]
PHONE_EVENT_FIELDS = [
    "paragraph_id",
    "phrase_idx",
    "syllable_idx",
    "global_syllable_idx",
    "syllable",
    "phone_idx",
    "phone",
    "phone_role",
    "viseme_id",
    "start_frame",
    "end_frame",
    "start_time_ms",
    "end_time_ms",
    "dominance",
    "motion_profile",
]
MIX_FIELDS = [
    "frame_id",
    "time_ms",
    "phrase_idx",
    "syllable_idx",
    "global_syllable_idx",
    "syllable",
    "start_viseme",
    "end_viseme",
    "alpha",
]
MOUTH_FIELDS = [
    "frame_id",
    "time_ms",
    "syllable",
    "start_v",
    "end_v",
    "alpha",
    "rms_amp",
    *MOUTH_CSV_NAMES,
]
FULL_FIELDS = ["frame_id", "time_ms", *SERVO_NAMES]


def parse_args():
    parser = argparse.ArgumentParser(description="Run paragraph-level robot viseme sync pipeline.")
    parser.add_argument("--paragraph-id", default="P001")
    parser.add_argument("--text", default=None)
    parser.add_argument("--text-file", default=None)
    parser.add_argument("--audio", default=None, help="Existing WAV. If omitted, Windows TTS is used.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--voice", default=None)
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--alignment-source", choices=["auto", "estimated", "tts-viseme"], default="auto")
    parser.add_argument("--phone-alignment", default=None, help="Existing phone_alignment CSV.")
    parser.add_argument("--tts-events", default=None, help="Existing or generated Windows TTS events JSON.")
    parser.add_argument("--control-hz", type=float, default=25.0)
    parser.add_argument("--rms-threshold", type=float, default=0.10)
    parser.add_argument("--rms-smooth-window", type=int, default=3)
    parser.add_argument("--min-active-frames", type=int, default=2)
    parser.add_argument("--max-silence-gap-fill", type=int, default=2)
    parser.add_argument("--timing-mode", choices=["phone", "syllable"], default="phone")
    parser.add_argument("--alpha-curve", choices=["linear", "smoothstep", "smootherstep"], default="smootherstep")
    parser.add_argument("--disable-rms-amplitude", action="store_true")
    parser.add_argument("--rms-amp-min", type=float, default=0.72)
    parser.add_argument("--rms-amp-max", type=float, default=1.08)
    parser.add_argument("--rms-amp-percentile", type=float, default=0.92)
    parser.add_argument("--rms-amp-smooth-window", type=int, default=3)
    parser.add_argument("--smooth-beta", type=float, default=0.75)
    parser.add_argument("--max-delta", type=float, default=0.14)
    parser.add_argument("--execute", action="store_true", help="Play audio and send the safe 16ch trajectory.")
    parser.add_argument("--dry-run-execute", action="store_true")
    parser.add_argument("--port", default="COM8")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--servo-audio-offset-ms", type=float, default=0.0)
    return parser.parse_args()


def read_text(args) -> str:
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8")
    if args.text:
        return args.text
    raise ValueError("Provide --text or --text-file")


def synthesize_tts(text: str, out_path: Path, args, events_path: Path | None = None):
    command = [
        sys.executable,
        str(ROOT / "tts_windows.py"),
        "--text",
        text,
        "--out",
        str(out_path),
        "--rate",
        str(args.rate),
        "--volume",
        str(args.volume),
    ]
    if args.voice:
        command.extend(["--voice", args.voice])
    if events_path:
        command.extend(["--events-out", str(events_path)])
    subprocess.run(command, cwd=ROOT, check=True)


def prepare_audio(text: str, sample_dir: Path, args) -> tuple[Path, Path | None]:
    out_path = sample_dir / f"{args.paragraph_id}.wav"
    if args.audio:
        source = Path(args.audio).resolve()
        if source != out_path.resolve():
            shutil.copy2(source, out_path)
        tts_events = Path(args.tts_events).resolve() if args.tts_events else None
        return out_path, tts_events

    events_path = (
        Path(args.tts_events).resolve()
        if args.tts_events
        else sample_dir / f"{args.paragraph_id}_tts_events.json"
    )
    synthesize_tts(text, out_path, args, events_path=events_path)
    return out_path, events_path if events_path.is_file() else None


def main():
    args = parse_args()
    paragraph_id = args.paragraph_id
    config_dir = (ROOT / args.config_dir).resolve()
    data_dir = (ROOT / args.data_dir).resolve()
    sample_dir = ensure_dir(data_dir / paragraph_id)

    ensure_default_configs(ROOT, config_dir)

    text = read_text(args)
    text_path = sample_dir / f"{paragraph_id}_text.txt"
    text_path.write_text(text, encoding="utf-8")

    phrase_doc = build_phrase_doc(paragraph_id, text)
    write_json(sample_dir / f"{paragraph_id}_phrase.json", phrase_doc)

    audio_path, tts_events_path = prepare_audio(text, sample_dir, args)

    pinyin_doc = phrases_to_pinyin(paragraph_id, phrase_doc)
    write_json(sample_dir / f"{paragraph_id}_pinyin.json", pinyin_doc)

    mapping = load_mapping(config_dir / "pinyin_to_viseme.json")
    syllable_doc = map_pinyin_to_visemes(paragraph_id, pinyin_doc, mapping)
    write_json(sample_dir / f"{paragraph_id}_syllable_viseme.json", syllable_doc)

    rms_rows, rms_meta = extract_rms_envelope(
        audio_path,
        control_hz=args.control_hz,
        threshold=args.rms_threshold,
        smooth_window=args.rms_smooth_window,
        min_active_frames=args.min_active_frames,
        max_silence_gap_fill=args.max_silence_gap_fill,
    )
    write_csv(sample_dir / f"{paragraph_id}_rms.csv", rms_rows, RMS_FIELDS)

    segments = detect_active_segments(rms_rows, control_hz=args.control_hz)
    write_csv(sample_dir / f"{paragraph_id}_active_segments.csv", segments, SEGMENT_FIELDS)

    phrase_segments = align_phrases_to_segments(
        paragraph_id,
        phrase_doc["phrases"],
        segments,
        n_frames=len(rms_rows),
        control_hz=args.control_hz,
    )
    write_csv(sample_dir / f"{paragraph_id}_phrase_segment.csv", phrase_segments, PHRASE_SEGMENT_FIELDS)

    allocation = allocate_syllable_frames(paragraph_id, syllable_doc, phrase_segments)
    write_csv(sample_dir / f"{paragraph_id}_allocation.csv", allocation, ALLOCATION_FIELDS)

    phone_alignment, phone_alignment_source = build_phone_alignment_for_run(
        paragraph_id=paragraph_id,
        syllable_doc=syllable_doc,
        phrase_segments=phrase_segments,
        args=args,
        tts_events_path=tts_events_path,
        rms_rows=rms_rows,
    )
    write_csv(sample_dir / f"{paragraph_id}_phone_alignment.csv", phone_alignment, PHONE_ALIGNMENT_FIELDS)

    phone_events = build_phone_events_from_alignment(paragraph_id, phone_alignment)
    write_csv(sample_dir / f"{paragraph_id}_phone_events.csv", phone_events, PHONE_EVENT_FIELDS)

    if args.timing_mode == "phone":
        mix_rows = compute_phone_event_mix(phone_events, control_hz=args.control_hz, curve=args.alpha_curve)
    else:
        mix_rows = compute_alpha_mix(allocation, control_hz=args.control_hz, curve=args.alpha_curve)
    write_csv(sample_dir / f"{paragraph_id}_viseme_mix.csv", mix_rows, MIX_FIELDS)

    neutral_rest = load_neutral_rest(config_dir, ROOT / "neutral_rest.json")
    viseme_poses = load_viseme_poses(config_dir, ROOT / "viseme_poses_6d.json")
    mouth_rows = generate_mouth_trajectory(
        mix_rows,
        n_frames=len(rms_rows),
        viseme_poses=viseme_poses,
        neutral_mouth=neutral_mouth_from_rest(neutral_rest),
        rms_rows=rms_rows,
        use_rms_amplitude=not args.disable_rms_amplitude,
        rms_amp_min=args.rms_amp_min,
        rms_amp_max=args.rms_amp_max,
        rms_amp_percentile=args.rms_amp_percentile,
        rms_amp_smooth_window=args.rms_amp_smooth_window,
    )
    write_csv(sample_dir / f"{paragraph_id}_servo_mouth.csv", mouth_rows, MOUTH_FIELDS)

    mapping_report = build_viseme_mapping_report(
        phone_alignment,
        mouth_rows,
        viseme_poses,
        control_hz=args.control_hz,
    )
    mapping_report_path = write_csv(
        sample_dir / f"{paragraph_id}_viseme_mapping_report.csv",
        mapping_report,
        MAPPING_REPORT_FIELDS,
    )

    full_rows = build_16ch_trajectory(mouth_rows, neutral_rest, control_hz=args.control_hz)
    full_rows = handle_silence_frames(
        full_rows,
        rms_rows,
        neutral_rest,
        control_hz=args.control_hz,
    )
    write_csv(sample_dir / f"{paragraph_id}_servo_target_16ch.csv", full_rows, FULL_FIELDS)

    limits = load_servo_limits(config_dir)
    safe_rows = clamp_servo_values(full_rows, limits)
    safe_rows = smooth_trajectory(safe_rows, beta=args.smooth_beta, max_delta=args.max_delta)
    safe_path = write_csv(sample_dir / f"{paragraph_id}_servo_target_16ch_safe.csv", safe_rows, FULL_FIELDS)

    meta = {
        "paragraph_id": paragraph_id,
        "text": text,
        "audio": str(audio_path),
        "tts_events": str(tts_events_path) if tts_events_path else None,
        "config_dir": str(config_dir),
        "sample_dir": str(sample_dir),
        "control_hz": args.control_hz,
        "timing_mode": args.timing_mode,
        "alpha_curve": args.alpha_curve,
        "rms_amplitude": {
            "enabled": not args.disable_rms_amplitude,
            "min": args.rms_amp_min,
            "max": args.rms_amp_max,
            "percentile": args.rms_amp_percentile,
            "smooth_window": args.rms_amp_smooth_window,
        },
        "rms": rms_meta,
        "phrases": len(phrase_doc["phrases"]),
        "syllables": len(syllable_doc["syllables"]),
        "phrase_segments": len(phrase_segments),
        "phrase_segment_fallbacks": sum(int(row.get("fallback", 0)) for row in phrase_segments),
        "phone_alignment": {
            "source": phone_alignment_source,
            "phones": len(phone_alignment),
        },
        "phone_events": len(phone_events),
        "active_segments": len(segments),
        "viseme_mapping_report": str(mapping_report_path),
        "safe_trajectory": str(safe_path),
        "mouth_servo_names": MOUTH_SERVO_NAMES,
    }
    write_json(sample_dir / f"{paragraph_id}_pipeline_meta.json", meta)
    ensure_evaluation_templates(sample_dir, paragraph_id)

    if args.execute:
        play_audio_and_send_servos(
            audio_path=audio_path,
            servo_csv=safe_path,
            log_path=sample_dir / f"{paragraph_id}_execution_log.csv",
            port=args.port,
            baudrate=args.baudrate,
            servo_audio_offset_ms=args.servo_audio_offset_ms,
            dry_run=args.dry_run_execute,
        )

    print(json.dumps(meta, indent=2, ensure_ascii=False))


def build_phone_alignment_for_run(
    paragraph_id: str,
    syllable_doc: dict,
    phrase_segments: list[dict],
    args,
    tts_events_path: Path | None,
    rms_rows: list[dict],
) -> tuple[list[dict], str]:
    if args.phone_alignment:
        source_path = Path(args.phone_alignment).resolve()
        return read_csv(source_path), f"external_csv:{source_path}"

    if (
        args.alignment_source in {"auto", "tts-viseme"}
        and tts_events_path
        and tts_events_path.is_file()
    ):
        rows = build_tts_viseme_alignment(
            paragraph_id,
            syllable_doc,
            phrase_segments,
            tts_events_path,
            control_hz=args.control_hz,
            rms_rows=rms_rows,
        )
        if rows:
            return rows, "tts_viseme"
        if args.alignment_source == "tts-viseme":
            raise RuntimeError(f"No usable viseme events found in {tts_events_path}")

    if args.alignment_source == "tts-viseme":
        raise RuntimeError("TTS viseme alignment requested, but no --tts-events file is available.")

    rows = build_estimated_phone_alignment(
        paragraph_id,
        syllable_doc,
        phrase_segments,
        control_hz=args.control_hz,
    )
    return rows, "estimated"


if __name__ == "__main__":
    main()
