# Direct Robot Mouth Pipeline

This folder is the standalone fallback pipeline for the robot mouth.
It does not use Wav2Lip, VAE, or FAT.

Pipeline:

```text
text -> Windows TTS -> audio energy sync -> pinyin/viseme sync -> smoothing -> serial replay
```

The pinyin/viseme step uses the 8-class Mandarin viseme table from the
uploaded emotion-consistent lip-sync paper:

```text
0: p,b,m,basic
1: f
2: t,d,n,l,ch,r,sh,zh
3: w
4: k,g,h,eng,e,en,ing
5: j,q,x,y,i,z,c,s
6: o,ong
7: an,a,ang
```

For each pinyin syllable, the script maps the initial and final to viseme IDs.
If the final viseme is larger than the initial viseme, it generates a smooth
transition inside the syllable; otherwise the final viseme covers the initial
one. This follows the paper's simplified initial/final viseme transition rule.

## Calibrate Viseme Poses

Each viseme needs a robot-specific 6DOF target pose:

```text
mouth_open, mouth_up_corner_l, mouth_up_corner_r,
mouth_lip_upper_l, mouth_lip_upper_r, mouth_lip_lower
```

Value ranges:

```text
mouth_open: 0..1, 0 = fully closed, 1 = fully open
other mouth servos: -1..1, 0 = neutral/middle
```

Run the browser-based calibration tool:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe servo_gui.py --host 127.0.0.1 --port 5050
```

Then open:

```text
http://127.0.0.1:5050
```

Use the sliders to adjust each V0–V7 mouth pose, click `发送` to test it,
click `保存` to update `viseme_poses_6d.json`, and click `导出 CSV` to refresh
the pipeline config files under `config/`.

Suggested visual targets:

```text
0 p,b,m,basic       lips closed or slightly pressed
1 f                 lower lip/upper lip contact feel
2 t,d,n,l,ch,r...   small opening, neutral corners
3 w                 rounded/puckered mouth, corners inward
4 k,g,h,e,en...     medium neutral opening
5 j,q,x,y,i,z...    wide/narrow smile-like shape
6 o,ong             rounded open mouth
7 an,a,ang          largest open mouth
```

After `save`, `text_to_robot_direct.py` automatically uses
`direct_robot_pipeline/viseme_poses_6d.json`.

## Visual Servo GUI

Run the browser-based calibration page:

```powershell
python servo_gui.py --dry-run --host 127.0.0.1 --port 5050
```

Open:

```text
http://127.0.0.1:5050
```

The page starts safely in dry-run mode. To drive the robot, uncheck
`模拟发送`, keep the serial port as `COM8` or change it, then click `连接`.
The GUI edits and saves `viseme_poses_6d.json`, and can also export pipeline config files:

```text
config/neutral_rest.csv
config/neutral_viseme_pose_final.csv
config/viseme_meta.csv
```

## Paragraph Viseme Sync Pipeline

The refactored pipeline follows `robot_viseme_sync_pipeline.md`. One run creates a paragraph sample folder such as `data/P001/` with phrase, pinyin, RMS, active segment, allocation, alpha mix, mouth trajectory, and final 16-channel servo CSV files.

Generate a sample with Windows TTS:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P001 `
  --text "大家好，欢迎来到实验室。今天我们来介绍机器人嘴型同步系统。"
```

For longer Chinese text, a UTF-8 text file is safer:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P001 `
  --text-file data\P001\P001_text.txt
```

Use an existing WAV instead of TTS:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P001 `
  --text-file data\P001\P001_text.txt `
  --audio data\P001\P001.wav
```

Important outputs:

```text
data/P001/P001_phrase.json
data/P001/P001_pinyin.json
data/P001/P001_syllable_viseme.json
data/P001/P001_rms.csv
data/P001/P001_active_segments.csv
data/P001/P001_phrase_segment.csv
data/P001/P001_allocation.csv
data/P001/P001_viseme_mix.csv
data/P001/P001_servo_mouth.csv
data/P001/P001_servo_target_16ch.csv
data/P001/P001_servo_target_16ch_safe.csv
data/P001/P001_pipeline_meta.json
data/P001/human_rating.csv
data/P001/issue_log.csv
```

Dry-run execution prints packets and writes an execution log:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P001 `
  --text-file data\P001\P001_text.txt `
  --audio data\P001\P001.wav `
  --execute `
  --dry-run-execute
```

Robot execution:

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P001 `
  --text-file data\P001\P001_text.txt `
  --audio data\P001\P001.wav `
  --execute `
  --port COM8 `
  --servo-audio-offset-ms 0
```

Required Python packages:

```text
numpy
flask
pyserial
pypinyin
```

Notes:

- Run this on Windows for `tts_windows.py`, because it uses Windows SAPI.
- The robot serial protocol sends a 16-value text array plus terminator.
- Mouth channels are indices 8 to 13 in the full robot command.
- Default port is `COM8`; change it with `--port`.
- `config/` is auto-created from `viseme_poses_6d.json` and `neutral_rest.json` if the CSV config files are missing.
