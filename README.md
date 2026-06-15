# 机器人嘴型同步 Pipeline

这个目录是 16 路舵机机器人头部的中性嘴型同步流程。当前版本不使用 Wav2Lip、VAE 或 FAT，核心目标是：

```text
中文文本/语音
  -> 拼音
  -> start_viseme / end_viseme
  -> 音频 RMS 找说话区间
  -> 音节帧分配
  -> 声母/韵母 phone events
  -> 每帧 alpha
  -> 6 路嘴部舵机
  -> 16 路完整舵机轨迹
  -> 播放音频并同步发送舵机
```

最重要的原则是：不要给每个音节写固定时长。当前仍然用音频 RMS active region 决定每句话/音节占多少帧；然后在音节内部拆成声母、韵母事件，让闭合、释放、元音保持更接近真实发音动作。

## Viseme 表

当前使用 8 类中文基础 viseme：

```text
V0: b,p,m
V1: f
V2: d,t,n,l,zh,ch,sh,r
V3: w,u
V4: e,en,eng,k,g,h
V5: i,j,q,x,z,c,s
V6: o,ong
V7: a,an,ang
```

拼音音节会映射成起止 viseme，例如：

```text
ba  = V0 -> V7
ma  = V0 -> V7
wo  = V3 -> V6
shi = V2 -> V5
yi  = V5 -> V5
```

## 当前过渡方式

默认使用 `--timing-mode phone`：

```text
RMS active segment
  -> phrase 时间段
  -> 音节帧区间
  -> 声母 phone event + 韵母 phone event
  -> 每帧 alpha
```

这一步不是严格的 forced alignment，还没有从音频里测出真正的音素边界。它是在 RMS 分出的音节时间里，根据拼音声母/韵母做经验拆分：

```text
b,p,m 这类闭唇声母：先保持闭合，再快速释放到韵母嘴型
f      这类唇齿声母：保留较强的声母占比
d,t,n,l,zh,ch,sh,r,z,c,s：声母占比较短，较快进入韵母
纯韵母或 start_viseme=end_viseme：保持单一嘴型
```

如果想回到旧版“一个音节内 start_viseme 线性过渡到 end_viseme”，可以加：

```text
--timing-mode syllable
```

## 舵机范围

每个 viseme 对应 6 路嘴部舵机：

```text
mouth_open
mouth_up_corner_l
mouth_up_corner_r
mouth_lip_upper_l
mouth_lip_upper_r
mouth_lip_lower
```

数值范围：

```text
mouth_open: 0..1，0 = 完全闭嘴，1 = 完全张开
其他嘴部舵机: -1..1，0 = 中间状态
```

## config 目录

`config/` 保存全局配置。pipeline 会优先读取这里的文件；如果文件不存在，才会根据默认值或旧 JSON 自动生成。

`config/neutral_rest.csv`  
机器人 16 路中性姿态。静音时、非嘴部舵机补全时会使用它。

`config/neutral_viseme_pose_final.csv`  
8 个静态 viseme 嘴型表。pipeline 生成嘴部轨迹时会查这张表并做插值，这是最关键的配置文件。

`config/viseme_meta.csv`  
8 个 viseme 的元信息，包括代表音、开口度和形状标签。主要用于检查、解释和后续分析。

`config/pinyin_to_viseme.json`  
拼音到 viseme 的映射规则，决定 `*_syllable_viseme.json` 如何生成。

`config/servo_limits.csv`  
每个舵机的安全范围。生成 `*_servo_target_16ch_safe.csv` 时会使用它做裁剪。

## 标定 8 个 Viseme

启动网页调参工具：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe servo_gui.py --host 127.0.0.1 --port 5050
```

打开：

```text
http://127.0.0.1:5050
```

操作流程：

```text
选择 V0-V7
  -> 拖动 6 个嘴部舵机滑杆
  -> 点击“发送”观察机器人真实嘴型
  -> 满意后点击“保存”
  -> 点击“导出 CSV”
```

保存和导出的关系：

```text
点击“保存”
  -> 更新 viseme_poses_6d.json

点击“导出 CSV”
  -> 更新 config/neutral_rest.csv
  -> 更新 config/neutral_viseme_pose_final.csv
  -> 更新 config/viseme_meta.csv
  -> 更新 config/servo_limits.csv
```

pipeline 实际优先读取的是 `config/neutral_viseme_pose_final.csv`。所以真实机器人标定完成后，记得点击“导出 CSV”，然后重新运行 pipeline。

建议嘴型目标：

```text
V0 b,p,m              闭唇或接近闭唇
V1 f                  下唇略靠近上齿
V2 d,t,n,l,zh,ch,sh,r 小开口，中性过渡嘴型
V3 w,u                圆唇，小开口，收口
V4 e,en,eng,k,g,h     中等开口，自然嘴型
V5 i,j,q,x,z,c,s      扁嘴，小开口，横向展开，但不要像笑
V6 o,ong              圆唇，中等或较大开口
V7 a,an,ang           大开口
```

## 生成一段新的文本轨迹

推荐用 UTF-8 文本文件输入中文。

例如新建：

```text
data/P002/P002_text.txt
```

里面写：

```text
大家好，今天我们测试机器人嘴型同步系统。
```

生成音频和轨迹：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P002 `
  --text-file data\P002\P002_text.txt
```

如果已有自己的音频：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P002 `
  --text-file data\P002\P002_text.txt `
  --audio data\P002\P002.wav
```

直接命令行输入短文本也可以：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P002 `
  --text "你好，我是机器人。"
```

## 执行机器人

先 dry-run，不动机器人，只打印部分串口包并写执行日志：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P002 `
  --text-file data\P002\P002_text.txt `
  --audio data\P002\P002.wav `
  --execute `
  --dry-run-execute
```

真实执行：

```powershell
D:\Anaconda_envs\envs\DDPO\python.exe run_viseme_pipeline.py `
  --paragraph-id P002 `
  --text-file data\P002\P002_text.txt `
  --audio data\P002\P002.wav `
  --execute `
  --port COM8 `
  --servo-audio-offset-ms 0
```

如果嘴型整体偏早或偏晚，可以调：

```text
--servo-audio-offset-ms
```

嘴型早了，增大 offset；嘴型晚了，减小 offset。

## data 输出文件链路

以 `data/P002/` 为例，生成文件是一环扣一环的：

```text
P002_text.txt
  -> P002_phrase.json
  -> P002_pinyin.json
  -> P002_syllable_viseme.json

P002.wav
  -> P002_rms.csv
  -> P002_active_segments.csv
  -> P002_phrase_segment.csv

P002_syllable_viseme.json + P002_phrase_segment.csv
  -> P002_allocation.csv
  -> P002_phone_events.csv
  -> P002_viseme_mix.csv
  -> P002_servo_mouth.csv
  -> P002_servo_target_16ch.csv
  -> P002_servo_target_16ch_safe.csv
```

`P002_text.txt`  
原始中文文本。

`P002.wav`  
整段语音音频。可以由 Windows TTS 自动生成，也可以由 `--audio` 指定已有 wav。

`P002_phrase.json`  
按标点切出来的 phrase。它只处理文本分段，还没有时间信息。

`P002_pinyin.json`  
每个 phrase 转成拼音音节序列。

`P002_syllable_viseme.json`  
每个拼音音节映射成 `start_viseme` 和 `end_viseme`。例如 `ba = V0 -> V7`，`shi = V2 -> V5`。

`P002_rms.csv`  
音频 RMS 能量表。默认 25 Hz，也就是每 40 ms 一帧。`active=1` 表示这一帧被检测为有效说话。

`P002_active_segments.csv`  
把连续的 active 帧合并成语音片段。这是音频侧的说话区间。

`P002_phrase_segment.csv`  
把文本 phrase 和音频 active segment 对齐。现在会优先一一对应；如果 RMS 检出很多小段，会按文本长度比例分配，并优先把边界放在较长静音处；如果 RMS 信息不足，才按整段比例切分并把 `fallback` 标成 1。

`P002_allocation.csv`  
把每个音节分配到具体帧区间。这是时间分配的核心结果，说明每个音节占哪些 audio frames。

`P002_phone_events.csv`  
默认 `phone` 模式下生成。它把每个音节内部进一步拆成声母/韵母事件，记录每个事件的帧区间、对应 viseme、dominance 和 motion_profile。它是我们把“音节平均过渡”改成“闭合-释放-韵母保持”的关键中间层。

`P002_viseme_mix.csv`  
展开每一帧的 `alpha`。默认 `phone` 模式下，它来自 `P002_phone_events.csv`；旧版 `syllable` 模式下，它来自 `P002_allocation.csv`。`alpha=0` 表示完全接近 `start_viseme`，`alpha=1` 表示完全接近 `end_viseme`。

`P002_servo_mouth.csv`  
根据 `start_viseme`、`end_viseme` 和 `alpha`，查 `config/neutral_viseme_pose_final.csv`，插值得到 6 路嘴部舵机轨迹。

`P002_servo_target_16ch.csv`  
把 6 路嘴部轨迹插入 16 路完整舵机命令。非嘴部舵机来自 `config/neutral_rest.csv`。

`P002_servo_target_16ch_safe.csv`  
最终用于执行的安全轨迹。在 `P002_servo_target_16ch.csv` 基础上做了舵机范围裁剪、最大步长限制和平滑。

`P002_pipeline_meta.json`  
记录本次运行参数，包括文本、音频路径、控制频率、RMS 参数、生成文件路径等。

`P002_execution_log.csv`  
使用 `--execute` 时生成，记录每帧发送时间、目标音频时间、嘴部目标值和发送是否成功。

`human_rating.csv`  
人工评分表，用于记录嘴型同步性、viseme 清晰度、自然度和总体评分。

`issue_log.csv`  
问题记录表，用于记录具体问题，例如闭唇不明显、嘴型整体偏晚、动作跳变等。

## 常用参数

```text
--control-hz              控制频率，默认 25 Hz
--rms-threshold           RMS active 阈值，默认 0.10
--rms-smooth-window       RMS 平滑窗口，默认 3 帧
--min-active-frames       最短 active 段，默认 2 帧
--max-silence-gap-fill    填补短静音断裂，默认 2 帧
--timing-mode             时间展开模式，phone 或 syllable，默认 phone
--alpha-curve             alpha 曲线，linear、smoothstep 或 smootherstep，默认 smootherstep
--smooth-beta             舵机低通平滑系数，默认 0.75
--max-delta               每帧最大变化，默认 0.14
--servo-audio-offset-ms   音频和舵机全局偏移
```

## 依赖

```text
numpy
flask
pyserial
pypinyin
```

安装：

```powershell
pip install -r requirements.txt
```

## 备注

- `tts_windows.py` 使用 Windows SAPI，所以 TTS 生成需要在 Windows 上运行。
- 串口协议发送 16 个数值组成的文本数组，并以换行符结尾。
- 嘴部舵机在完整 16 路命令中的索引是 8 到 13。
- 默认串口是 `COM8`，可以通过 `--port` 修改。
- `config/` 里的文件优先级最高；只有文件不存在时才会自动生成默认配置。
