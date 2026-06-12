from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

from .constants import MOUTH_SERVO_NAMES, SERVO_NAMES
from .io_utils import read_csv, write_csv


def format_packet(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.2f}" for v in values) + "]"


def play_audio_async(audio_path: str | Path):
    try:
        import winsound

        winsound.PlaySound(str(audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as exc:
        print(f"audio playback skipped: {exc}")


def play_audio_and_send_servos(
    audio_path: str | Path,
    servo_csv: str | Path,
    log_path: str | Path,
    port: str = "COM8",
    baudrate: int = 115200,
    servo_audio_offset_ms: float = 0.0,
    dry_run: bool = False,
):
    rows = read_csv(servo_csv)
    if not rows:
        raise ValueError("No servo rows to replay.")

    ser = None
    if not dry_run:
        if serial is None:
            raise RuntimeError("pyserial is required for robot execution.")
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=0.1, stopbits=serial.STOPBITS_ONE)
        time.sleep(0.5)

    log_rows = []
    start_time = time.perf_counter()
    play_audio_async(audio_path)

    try:
        for row in rows:
            target_ms = float(row["time_ms"]) + float(servo_audio_offset_ms)
            target_time = start_time + target_ms / 1000.0
            while time.perf_counter() < target_time:
                time.sleep(0.001)

            values = [float(row[name]) for name in SERVO_NAMES]
            packet = format_packet(values)
            ok = True
            if dry_run:
                if int(row["frame_id"]) % 25 == 0:
                    print(packet)
            else:
                try:
                    ser.write(packet.encode("utf-8") + b"\n")
                    ser.flush()
                except Exception:
                    ok = False

            now_ms = (time.perf_counter() - start_time) * 1000.0
            log = {
                "time_ms": round(now_ms, 3),
                "audio_time_ms": round(target_ms, 3),
                "frame_id": int(row["frame_id"]),
                "send_success": int(ok),
            }
            for name in MOUTH_SERVO_NAMES:
                log[f"{name}_target"] = row[name]
            log_rows.append(log)
    finally:
        if ser is not None:
            ser.close()

    fieldnames = [
        "time_ms",
        "audio_time_ms",
        "frame_id",
        *[f"{name}_target" for name in MOUTH_SERVO_NAMES],
        "send_success",
    ]
    write_csv(log_path, log_rows, fieldnames)
    return log_rows


def main():
    parser = argparse.ArgumentParser(description="Play audio and send 16-channel servo trajectory.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--servo-csv", required=True)
    parser.add_argument("--log", default=None)
    parser.add_argument("--port", default="COM8")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--servo-audio-offset-ms", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log_path = args.log or str(Path(args.servo_csv).with_name("execution_log.csv"))
    play_audio_and_send_servos(
        audio_path=args.audio,
        servo_csv=args.servo_csv,
        log_path=log_path,
        port=args.port,
        baudrate=args.baudrate,
        servo_audio_offset_ms=args.servo_audio_offset_ms,
        dry_run=args.dry_run,
    )
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()

