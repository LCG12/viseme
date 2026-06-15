#!/usr/bin/env python
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_TEXT = "爸爸妈妈你好，今天我们测试机器人嘴型同步。"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def run_powershell(script: str, env: dict[str, str] | None = None):
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        check=True,
        env=env,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Test Windows TTS timing events.")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--out-dir", default="data/tts_event_test")
    parser.add_argument("--voice", default=None)
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--list-voices", action="store_true")
    return parser.parse_args()


def list_voices():
    script = r"""
Add-Type -AssemblyName System.Speech
$ProgressPreference = "SilentlyContinue"
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.GetInstalledVoices() | ForEach-Object {
  $info = $_.VoiceInfo
  Write-Output "$($info.Name) | $($info.Culture) | $($info.Gender) | $($info.Age)"
}
$synth.Dispose()
"""
    run_powershell(script)


def synthesize_with_events(text: str, out_dir: Path, voice: str | None, rate: int, volume: int) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = (out_dir / "windows_tts_event_test.wav").resolve()
    events_path = (out_dir / "windows_tts_events.json").resolve()

    env = os.environ.copy()
    env["TTS_TEXT"] = text
    env["TTS_OUT"] = str(wav_path)
    env["TTS_EVENTS_OUT"] = str(events_path)
    env["TTS_RATE"] = str(rate)
    env["TTS_VOLUME"] = str(volume)
    env["TTS_VOICE"] = voice or ""

    script = r"""
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Add-Type -AssemblyName System.Speech

$script:events = New-Object System.Collections.ArrayList
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

if (-not [string]::IsNullOrWhiteSpace($env:TTS_VOICE)) {
  $synth.SelectVoice($env:TTS_VOICE)
}
$synth.Rate = [int]$env:TTS_RATE
$synth.Volume = [int]$env:TTS_VOLUME

$synth.add_PhonemeReached({
  param($sender, $e)
  [void]$script:events.Add([ordered]@{
    type = "phoneme"
    audio_position_ms = [math]::Round($e.AudioPosition.TotalMilliseconds, 3)
    duration_ms = [math]::Round($e.Duration.TotalMilliseconds, 3)
    phoneme = [string]$e.Phoneme
    next_phoneme = [string]$e.NextPhoneme
    emphasis = [string]$e.Emphasis
  })
})

$synth.add_VisemeReached({
  param($sender, $e)
  [void]$script:events.Add([ordered]@{
    type = "viseme"
    audio_position_ms = [math]::Round($e.AudioPosition.TotalMilliseconds, 3)
    duration_ms = [math]::Round($e.Duration.TotalMilliseconds, 3)
    viseme = [int]$e.Viseme
    next_viseme = [int]$e.NextViseme
    emphasis = [string]$e.Emphasis
  })
})

$synth.add_SpeakProgress({
  param($sender, $e)
  [void]$script:events.Add([ordered]@{
    type = "progress"
    audio_position_ms = [math]::Round($e.AudioPosition.TotalMilliseconds, 3)
    character_position = [int]$e.CharacterPosition
    character_count = [int]$e.CharacterCount
    text = [string]$e.Text
  })
})

$synth.SetOutputToWaveFile($env:TTS_OUT)
$synth.Speak($env:TTS_TEXT)
$voiceName = $synth.Voice.Name
$voiceCulture = $synth.Voice.Culture.Name
$synth.Dispose()

$counts = [ordered]@{
  phoneme = @($script:events | Where-Object { $_.type -eq "phoneme" }).Count
  viseme = @($script:events | Where-Object { $_.type -eq "viseme" }).Count
  progress = @($script:events | Where-Object { $_.type -eq "progress" }).Count
}

$result = [ordered]@{
  text = $env:TTS_TEXT
  voice = $voiceName
  culture = $voiceCulture
  wav = $env:TTS_OUT
  counts = $counts
  events = @($script:events | Sort-Object audio_position_ms, type)
}

$json = $result | ConvertTo-Json -Depth 8
Set-Content -LiteralPath $env:TTS_EVENTS_OUT -Value $json -Encoding UTF8
Write-Output "wav=$env:TTS_OUT"
Write-Output "events=$env:TTS_EVENTS_OUT"
Write-Output "phoneme_events=$($counts.phoneme)"
Write-Output "viseme_events=$($counts.viseme)"
Write-Output "progress_events=$($counts.progress)"
"""
    run_powershell(script, env=env)
    return wav_path, events_path


def print_summary(events_path: Path):
    data = json.loads(events_path.read_text(encoding="utf-8-sig"))
    print("\nSummary")
    print(f"  voice: {data.get('voice')} ({data.get('culture')})")
    print(f"  wav: {data.get('wav')}")
    print(f"  events: {events_path}")
    print(f"  counts: {data.get('counts')}")

    events = data.get("events", [])
    for event_type in ("phoneme", "viseme", "progress"):
        sample = sorted(
            [event for event in events if event.get("type") == event_type],
            key=lambda event: float(event.get("audio_position_ms", 0.0)),
        )[:8]
        print(f"\nFirst {event_type} events:")
        if not sample:
            print("  <none>")
            continue
        for event in sample:
            print("  " + json.dumps(event, ensure_ascii=False))


def main():
    args = parse_args()
    if args.list_voices:
        list_voices()
        return

    wav_path, events_path = synthesize_with_events(
        text=args.text,
        out_dir=(ROOT / args.out_dir).resolve(),
        voice=args.voice,
        rate=args.rate,
        volume=args.volume,
    )
    if not wav_path.is_file():
        raise RuntimeError(f"WAV was not created: {wav_path}")
    if not events_path.is_file():
        raise RuntimeError(f"Events JSON was not created: {events_path}")
    print_summary(events_path)


if __name__ == "__main__":
    main()
