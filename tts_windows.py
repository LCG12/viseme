import argparse
import base64
import os
import subprocess
from pathlib import Path


def run_powershell(script):
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Synthesize text to WAV with Windows SAPI.")
    parser.add_argument("--text", default=None)
    parser.add_argument("--text-file", default=None)
    parser.add_argument("--out", default="outputs/tts.wav")
    parser.add_argument("--voice", default=None, help="Optional installed Windows voice name.")
    parser.add_argument("--rate", type=int, default=0, help="Speech rate, usually -10 to 10.")
    parser.add_argument("--volume", type=int, default=100, help="Volume, 0 to 100.")
    parser.add_argument("--list-voices", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_voices:
        script = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.GetInstalledVoices() | ForEach-Object {
  $info = $_.VoiceInfo
  Write-Output "$($info.Name) | $($info.Culture) | $($info.Gender) | $($info.Age)"
}
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

    env = os.environ.copy()
    env["TTS_TEXT"] = text
    env["TTS_OUT"] = str(out_path)
    env["TTS_RATE"] = str(args.rate)
    env["TTS_VOLUME"] = str(args.volume)
    env["TTS_VOICE"] = args.voice or ""

    script = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if (-not [string]::IsNullOrWhiteSpace($env:TTS_VOICE)) {
  $synth.SelectVoice($env:TTS_VOICE)
}
$synth.Rate = [int]$env:TTS_RATE
$synth.Volume = [int]$env:TTS_VOLUME
$synth.SetOutputToWaveFile($env:TTS_OUT)
$synth.Speak($env:TTS_TEXT)
$synth.Dispose()
Write-Output $env:TTS_OUT
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        check=True,
        env=env,
    )
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
