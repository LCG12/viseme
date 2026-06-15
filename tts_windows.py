import argparse
import base64
import os
import subprocess
from pathlib import Path


def run_powershell(script, env=None):
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
    parser = argparse.ArgumentParser(description="Synthesize text to WAV with Windows SAPI.")
    parser.add_argument("--text", default=None)
    parser.add_argument("--text-file", default=None)
    parser.add_argument("--out", default="outputs/tts.wav")
    parser.add_argument("--voice", default=None, help="Optional installed Windows voice name.")
    parser.add_argument("--rate", type=int, default=0, help="Speech rate, usually -10 to 10.")
    parser.add_argument("--volume", type=int, default=100, help="Volume, 0 to 100.")
    parser.add_argument("--events-out", default=None, help="Optional JSON path for SAPI timing events.")
    parser.add_argument("--list-voices", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_voices:
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
        return

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        raise ValueError("Provide --text or --text-file")

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events_path = Path(args.events_out).resolve() if args.events_out else None
    if events_path:
        events_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["TTS_TEXT"] = text
    env["TTS_OUT"] = str(out_path)
    env["TTS_RATE"] = str(args.rate)
    env["TTS_VOLUME"] = str(args.volume)
    env["TTS_VOICE"] = args.voice or ""
    env["TTS_EVENTS_OUT"] = str(events_path or "")

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

if (-not [string]::IsNullOrWhiteSpace($env:TTS_EVENTS_OUT)) {
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
  Write-Output $env:TTS_EVENTS_OUT
}
Write-Output $env:TTS_OUT
"""
    run_powershell(script, env=env)
    print(f"saved {out_path}")
    if events_path:
        print(f"events {events_path}")


if __name__ == "__main__":
    main()
