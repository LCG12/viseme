# 机器人连续语音嘴型同步数据收集与技术实现流程

> 适用对象：16 舵机机器人头部平台  
> 当前目标：先完成 **中性嘴型同步**，暂不加入情绪、眉眼动态和脸颊情绪协同。  
> 核心思想：不要把每个音节写成固定运动原语，而是让 **音频 RMS 能量包络** 决定音节在时间轴上的占位。

---

## 0. 总体思路

整个系统的输入是一段中文文本，输出是机器人可以执行的 16 路舵机时间序列。

### 0.1 核心流程

```text
连续中文文本
    ↓
按标点切分 phrase
    ↓
TTS 生成整段语音 wav
    ↓
文本转拼音
    ↓
拼音音节 → start_viseme / end_viseme
    ↓
提取整段音频 RMS 能量包络
    ↓
检测 active speech regions
    ↓
active region 分配给 phrase
    ↓
每个 phrase 内部分配音节帧区间
    ↓
每个音节内部计算 alpha
    ↓
查 8 个静态 viseme 舵机姿态表
    ↓
插值得到每帧 6 路嘴部舵机值
    ↓
补全成 16 路舵机目标值
    ↓
播放语音并同步发送舵机指令
    ↓
录制机器人视频和执行日志
    ↓
人工评价并回溯修改
```

### 0.2 你们要避免的错误思路

不要做成：

```text
ba → 固定 start_hold_ms / transition_ms / end_hold_ms
ma → 固定 start_hold_ms / transition_ms / end_hold_ms
```

正确做法是：

```text
ba 在某条音频中占哪些 active frames
    ↓
ba = V0 → V7
    ↓
在这些 frames 内计算 alpha
    ↓
每帧插值得到舵机值
```

同一个 `ba` 在不同语速、不同句子里持续时间可以不同。

---

## 1. 阶段一：采集机器人中性静止姿态 neutral_rest

### 1.1 阶段目标

阶段一要得到机器人自然不说话时的 16 路中性姿态：

```text
neutral_rest.csv
```

它是后面所有嘴型、情绪和动作的基准。

### 1.2 为什么要做阶段一

如果没有中性姿态，后面就不知道：

```text
静音时嘴巴应该回到哪里？
非嘴部舵机应该保持什么值？
每个 viseme 是相对于哪个基准调整出来的？
```

阶段一相当于定义机器人自己的“自然脸”。

### 1.3 操作要求

把机器人调到：

```text
嘴巴自然闭合
嘴角不笑、不下垂
上唇和下唇自然
眉毛放松
眼皮自然打开
眼球看正前方
脸颊不抬
```

记录 16 个舵机值。

### 1.4 输出文件

文件名：

```text
dataset/00_calibration/neutral_rest.csv
```

字段：

| servo_id | servo_name        | value |
| --------:| ----------------- | -----:|
| 0        | brow_head_l       |       |
| 1        | brow_head_r       |       |
| 2        | eyelid_open_l     |       |
| 3        | eyelid_open_r     |       |
| 4        | eye_h_attention_l |       |
| 5        | eye_h_attention_r |       |
| 6        | eye_v_attention_l |       |
| 7        | eye_v_attention_r |       |
| 8        | mouth_open        |       |
| 9        | mouth_up_corner_l |       |
| 10       | mouth_up_corner_r |       |
| 11       | mouth_lip_upper_l |       |
| 12       | mouth_lip_upper_r |       |
| 13       | mouth_lip_lower   |       |
| 14       | cheek_l           |       |
| 15       | cheek_r           |       |

### 1.5 验收标准

阶段一完成后要检查：

```text
1. 机器人脸部自然、不夸张
2. 嘴巴处于自然闭合状态
3. 左右基本对称
4. 没有舵机卡死、抖动
5. 每次回到 neutral_rest 都能稳定复现
```

---

## 2. 阶段二：采集 8 个中性静态 viseme 嘴型

### 2.1 阶段目标

阶段二要得到：

```text
neutral_viseme_pose_raw.csv
neutral_viseme_pose_final.csv
```

也就是 8 个基础 viseme 对应的 6 路嘴部舵机姿态。

### 2.2 为什么要做阶段二

后面程序会做：

```text
ba = V0 → V7
```

但是程序必须知道：

```text
V0 闭唇到底对应哪些舵机值？
V7 大开口到底对应哪些舵机值？
```

阶段二就是建立“嘴型关键帧库”。

### 2.3 只调哪些舵机

阶段二只调 6 个嘴部舵机：

```text
8  mouth_open
9  mouth_up_corner_l
10 mouth_up_corner_r
11 mouth_lip_upper_l
12 mouth_lip_upper_r
13 mouth_lip_lower
```

其他舵机保持阶段一的 neutral_rest。

### 2.4 需要采集的 8 个 viseme

| viseme_id | 代表音                | 目标嘴型        |
| ---------:| ------------------ | ----------- |
| 0         | b,p,m              | 双唇闭合或接近闭合   |
| 1         | f                  | 小开口，下唇略靠近上齿 |
| 2         | d,t,n,l,zh,ch,sh,r | 小开口，中性过渡嘴型  |
| 3         | w,u                | 圆唇，小开口，收口   |
| 4         | e,en,eng,k,g,h     | 中等开口，自然嘴型   |
| 5         | i,j,q,x,z,c,s      | 扁嘴，小开口，横向展开 |
| 6         | o,ong              | 圆唇，中等或较大开口  |
| 7         | a,an,ang           | 大开口         |

### 2.5 每个 viseme 如何采集

每个 viseme 重复采集 3–5 次。

流程：

```text
机器人回 neutral_rest
    ↓
调出 V0
    ↓
保存 V0_T1
    ↓
拍 2–3 秒正面视频
    ↓
回 neutral_rest
    ↓
重新调 V0
    ↓
保存 V0_T2
    ↓
重复 3–5 次
```

V1–V7 同样做。

### 2.6 输出文件：raw 表

```text
dataset/01_static_viseme/neutral_viseme_pose_raw.csv
```

| sample_id | viseme_id | trial | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip | video_file | notes |
| --------- | ---------:| -----:| ----------:| --------:| --------:| -----------:| -----------:| ---------:| ---------- | ----- |
| V0_T1     | 0         | 1     |            |          |          |             |             |           | V0_T1.mp4  | 闭唇    |
| V0_T2     | 0         | 2     |            |          |          |             |             |           | V0_T2.mp4  |       |
| V7_T1     | 7         | 1     |            |          |          |             |             |           | V7_T1.mp4  | 大开口   |

### 2.7 输出文件：final 表

从每个 viseme 的 3–5 个 trial 中选最自然的一组，或取平均，形成：

```text
dataset/01_static_viseme/neutral_viseme_pose_final.csv
```

| viseme_id | phonemes           | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip |
| ---------:| ------------------ | ----------:| --------:| --------:| -----------:| -----------:| ---------:|
| 0         | b,p,m              |            |          |          |             |             |           |
| 1         | f                  |            |          |          |             |             |           |
| 2         | d,t,n,l,zh,ch,sh,r |            |          |          |             |             |           |
| 3         | w,u                |            |          |          |             |             |           |
| 4         | e,en,eng,k,g,h     |            |          |          |             |             |           |
| 5         | i,j,q,x,z,c,s      |            |          |          |             |             |           |
| 6         | o,ong              |            |          |          |             |             |           |
| 7         | a,an,ang           |            |          |          |             |             |           |

### 2.8 验收标准

```text
V0 必须能看出闭唇
V3 和 V6 都是圆唇，但 V6 开口大于 V3
V5 是扁嘴，不是笑
V7 是大开口，不是惊讶表情
左右尽量对称
所有姿态都不越界、不抖动
```

---

## 3. 阶段三：建立 viseme 元信息和拼音映射规则

### 3.1 阶段目标

阶段三要得到：

```text
viseme_meta.csv
pinyin_to_viseme.json
```

阶段二只告诉系统：

```text
V0 长什么样
V1 长什么样
...
V7 长什么样
```

阶段三告诉系统：

```text
ba 应该用 V0 → V7
shi 应该用 V2 → V5
wo 应该用 V3 → V6
每个 V 的开口度是多少
```

### 3.2 开口度 aperture 怎么定义

你们目前只有：

```text
mouth_open 是 [0,1]
```

所以第一版直接定义：

```text
aperture = mouth_open
```

前提是：

```text
mouth_open = 0 表示闭嘴
mouth_open = 1 表示张嘴
```

如果方向相反，则用：

```text
aperture = 1 - mouth_open
```

其他嘴部舵机不要参与 aperture 计算，因为它们可能是角度、PWM 或其他单位，而且主要描述嘴角、上下唇形状，不直接代表开口大小。

### 3.3 输出文件：viseme_meta.csv

```text
dataset/01_static_viseme/viseme_meta.csv
```

| viseme_id | phonemes           | aperture        | shape_label       |
| ---------:| ------------------ | ---------------:| ----------------- |
| 0         | b,p,m              | V0 的 mouth_open | closed_lip        |
| 1         | f                  | V1 的 mouth_open | small_labiodental |
| 2         | d,t,n,l,zh,ch,sh,r | V2 的 mouth_open | small_open        |
| 3         | w,u                | V3 的 mouth_open | small_round       |
| 4         | e,en,eng,k,g,h     | V4 的 mouth_open | mid_open          |
| 5         | i,j,q,x,z,c,s      | V5 的 mouth_open | wide_flat         |
| 6         | o,ong              | V6 的 mouth_open | round_open        |
| 7         | a,an,ang           | V7 的 mouth_open | large_open        |

### 3.4 输出文件：pinyin_to_viseme.json

```json
{
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
    "y": 5
  },
  "final": {
    "a": 7,
    "an": 7,
    "ang": 7,
    "o": 6,
    "ong": 6,
    "u": 3,
    "e": 4,
    "en": 4,
    "eng": 4,
    "i": 5,
    "ing": 4
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
    "ri": [2, 5]
  }
}
```

### 3.5 验收标准

用这些音节测试：

| 音节  | 应输出     |
| --- | ------- |
| ba  | V0 → V7 |
| ma  | V0 → V7 |
| fa  | V1 → V7 |
| wa  | V3 → V7 |
| wu  | V3 → V3 |
| wo  | V3 → V6 |
| shi | V2 → V5 |
| yi  | V5 → V5 |
| ge  | V4 → V4 |
| a   | V7 → V7 |

全部输出正确，阶段三完成。

---

## 4. 阶段四：建立句子 / 段落音频语料

### 4.1 阶段目标

阶段四要得到中文文本、拼音和音频文件：

```text
sentence_dataset.csv
wav/*.wav
```

对于连续说话，建议每段作为一个样本：

```text
P001_text.txt
P001.wav
P001_phrase.json
```

### 4.2 为什么要做阶段四

因为你们的方法不是手动设置每个音节时长，而是让音频 RMS 决定时间分配。没有真实音频，就无法计算 active frames。

### 4.3 输入文本示例

```text
大家好，欢迎来到实验室。今天我们来介绍机器人嘴型同步系统。
```

保存为：

```text
dataset/P001/P001_text.txt
```

### 4.4 切分 phrase

按标点切分：

```text
大家好
欢迎来到实验室
今天我们来介绍机器人嘴型同步系统
```

保存为：

```text
dataset/P001/P001_phrase.json
```

格式：

```json
{
  "paragraph_id": "P001",
  "phrases": [
    {
      "phrase_idx": 0,
      "text": "大家好",
      "punctuation": "，"
    },
    {
      "phrase_idx": 1,
      "text": "欢迎来到实验室",
      "punctuation": "。"
    },
    {
      "phrase_idx": 2,
      "text": "今天我们来介绍机器人嘴型同步系统",
      "punctuation": "。"
    }
  ]
}
```

### 4.5 生成整段 TTS 音频

第一版建议 TTS 生成整段音频，而不是每个 phrase 分开生成。

```text
dataset/P001/P001.wav
```

建议参数：

```text
采样率：16000 Hz 或 22050 Hz
声道：单声道
格式：wav
```

### 4.6 验收标准

```text
音频能正常播放
音频开头结尾没有过长静音
文本和音频一致
phrase 数量合理
句子覆盖 V0–V7 的所有嘴型
```

---

## 5. 阶段五：文本转拼音，再转 start/end viseme

### 5.1 阶段目标

阶段五要得到：

```text
P001_pinyin.json
P001_syllable_viseme.json
```

它回答的问题是：

```text
每个拼音音节应该从哪个 viseme 过渡到哪个 viseme？
```

### 5.2 转拼音

示例：

```text
大家好 → da jia hao
欢迎来到实验室 → huan ying lai dao shi yan shi
```

保存：

```text
dataset/P001/P001_pinyin.json
```

格式：

```json
{
  "paragraph_id": "P001",
  "phrases": [
    {
      "phrase_idx": 0,
      "text": "大家好",
      "pinyin": ["da", "jia", "hao"]
    },
    {
      "phrase_idx": 1,
      "text": "欢迎来到实验室",
      "pinyin": ["huan", "ying", "lai", "dao", "shi", "yan", "shi"]
    }
  ]
}
```

### 5.3 拼音转 viseme

示例：

```text
da  = d + a  → V2 → V7
jia = j + ia → V5 → V7
hao = h + ao → V4 → V6 或 V4 → V7
wo  = w + o  → V3 → V6
shi = sh + i → V2 → V5
```

保存：

```text
dataset/P001/P001_syllable_viseme.json
```

示例：

```json
{
  "paragraph_id": "P001",
  "syllables": [
    {
      "global_syllable_idx": 0,
      "phrase_idx": 0,
      "syllable": "da",
      "initial": "d",
      "final": "a",
      "start_viseme": 2,
      "end_viseme": 7
    },
    {
      "global_syllable_idx": 1,
      "phrase_idx": 0,
      "syllable": "jia",
      "initial": "j",
      "final": "ia",
      "start_viseme": 5,
      "end_viseme": 7
    }
  ]
}
```

### 5.4 复合韵母简化规则

第一版可以这样定：

| 韵母   | end_viseme |
| ---- | ----------:|
| ia   | 7          |
| ao   | 6 或 7      |
| ai   | 5 或 7      |
| uo   | 6          |
| ua   | 7          |
| uang | 7          |
| ui   | 5          |
| iu   | 3 或 5      |

### 5.5 阶段五不做什么

阶段五不处理时间，不提取 RMS，不生成舵机轨迹。

它只做：

```text
拼音音节 → start_viseme / end_viseme
```

---

## 6. 阶段六：提取 RMS 能量包络

### 6.1 阶段目标

阶段六要得到：

```text
P001_rms.csv
```

它回答的问题是：

```text
整段音频中每一帧是不是 active speech frame？
```

### 6.2 为什么要做阶段六

后面不手动设每个音节时长，而是根据语音能量包络决定音节在时间轴上的位置。

### 6.3 控制频率

建议：

```text
control_hz = 25
frame_ms = 40
```

也就是每 40 ms 生成一帧舵机目标值。

### 6.4 计算 RMS

对每个 40 ms 音频帧：

```text
rms = sqrt(mean(audio_frame^2))
rms_norm = rms / max_rms
```

判断 active：

```text
active = 1 if rms_norm > threshold else 0
```

建议参数：

```text
threshold = 0.08 ~ 0.12
smooth_window = 3 frames
min_active_frames = 2
max_silence_gap_fill = 2 frames
```

### 6.5 输出文件

```text
dataset/P001/P001_rms.csv
```

| frame_id | time_ms | rms | rms_norm | active |
| --------:| -------:| ---:| --------:| ------:|
| 0        | 0       |     |          | 0      |
| 1        | 40      |     |          | 0      |
| 2        | 80      |     |          | 1      |
| 3        | 120     |     |          | 1      |

### 6.6 平滑处理

原始 active 可能抖动：

```text
1 1 1 0 1 1
```

如果中间静音 gap 不超过 2 帧，可以填成：

```text
1 1 1 1 1 1
```

如果出现单帧 active：

```text
0 0 1 0 0
```

可以删除，因为很可能是噪声。

### 6.7 验收标准

```text
开头静音 active=0
结尾静音 active=0
主要说话区域 active=1
active 不应断断续续抖动太多
背景噪声不应被判为 active
```

---

## 7. 阶段七：检测 active segment 并分配给 phrase / 音节

### 7.1 阶段目标

阶段七要得到：

```text
P001_active_segments.csv
P001_phrase_segment.csv
P001_allocation.csv
```

它回答两个问题：

```text
每个 phrase 对应哪段 active segment？
每个音节占哪些帧？
```

### 7.2 检测 active segment

根据 `P001_rms.csv` 找出连续 active 区间。

输出：

```text
dataset/P001/P001_active_segments.csv
```

| segment_idx | start_frame | end_frame | start_time_ms | end_time_ms |
| -----------:| -----------:| ---------:| -------------:| -----------:|
| 0           | 5           | 22        | 200           | 880         |
| 1           | 30          | 78        | 1200          | 3120        |
| 2           | 92          | 180       | 3680          | 7200        |

### 7.3 phrase 对齐 active segment

如果 phrase 数量和 active segment 数量一致：

```text
phrase 0 → segment 0
phrase 1 → segment 1
phrase 2 → segment 2
```

输出：

```text
dataset/P001/P001_phrase_segment.csv
```

| phrase_idx | segment_idx | start_frame | end_frame | start_time_ms | end_time_ms |
| ----------:| -----------:| -----------:| ---------:| -------------:| -----------:|
| 0          | 0           | 5           | 22        | 200           | 880         |
| 1          | 1           | 30          | 78        | 1200          | 3120        |
| 2          | 2           | 92          | 180       | 3680          | 7200        |

如果数量不一致，第一版可以简单处理：

```text
把所有 active frames 当成一个大 segment
把所有音节按顺序分配进去
```

后续再改进 phrase 对齐。

### 7.4 每个 phrase 内部分配音节帧

例如：

```text
phrase 0 = 大家好 = da jia hao
active segment = frame 5–22
```

共有 18 帧，3 个音节。

平均分配：

```text
da  → frame 5–10
jia → frame 11–16
hao → frame 17–22
```

输出：

```text
dataset/P001/P001_allocation.csv
```

| paragraph_id | phrase_idx | syllable_idx | syllable | start_viseme | end_viseme | start_frame | end_frame | num_frames |
| ------------ | ----------:| ------------:| -------- | ------------:| ----------:| -----------:| ---------:| ----------:|
| P001         | 0          | 0            | da       | 2            | 7          | 5           | 10        | 6          |
| P001         | 0          | 1            | jia      | 5            | 7          | 11          | 16        | 6          |
| P001         | 0          | 2            | hao      | 4            | 6          | 17          | 22        | 6          |

### 7.5 验收标准

```text
每个音节都有 start_frame/end_frame
音节顺序和拼音顺序一致
所有帧区间落在 active segment 内
音节之间不重叠
每个音节至少 2–3 帧
```

---

## 8. 阶段八：计算每帧 viseme 混合系数 alpha

### 8.1 阶段目标

阶段八要得到：

```text
P001_viseme_mix.csv
```

它回答的问题是：

```text
在某个音节内部，每一帧更接近 start_viseme 还是 end_viseme？
```

### 8.2 计算公式

对于一个音节：

```text
start_frame = s
end_frame = e
```

某一帧 f 的线性 alpha：

```text
alpha = (f - s) / (e - s)
```

如果只有一帧，令：

```text
alpha = 1
```

或者保持 start_viseme。第一版建议保证每个音节至少 2–3 帧。

### 8.3 示例

```text
da: frame 5–10, V2 → V7
```

| frame_id | syllable | start_v | end_v | alpha |
| --------:| -------- | -------:| -----:| -----:|
| 5        | da       | 2       | 7     | 0.00  |
| 6        | da       | 2       | 7     | 0.20  |
| 7        | da       | 2       | 7     | 0.40  |
| 8        | da       | 2       | 7     | 0.60  |
| 9        | da       | 2       | 7     | 0.80  |
| 10       | da       | 2       | 7     | 1.00  |

### 8.4 输出文件

```text
dataset/P001/P001_viseme_mix.csv
```

| frame_id | time_ms | phrase_idx | syllable_idx | syllable | start_viseme | end_viseme | alpha |
| --------:| -------:| ----------:| ------------:| -------- | ------------:| ----------:| -----:|
| 5        | 200     | 0          | 0            | da       | 2            | 7          | 0.00  |
| 6        | 240     | 0          | 0            | da       | 2            | 7          | 0.20  |

### 8.5 平滑 alpha

第一版用线性 alpha。

如果运动太硬，可以使用：

```text
alpha_smooth = 3 * alpha^2 - 2 * alpha^3
```

它会让开始和结束更柔和。

### 8.6 阶段八不做什么

阶段八还不生成舵机值，只生成混合比例。

---

## 9. 阶段九：生成每帧嘴部 6 路舵机目标值

### 9.1 阶段目标

阶段九要得到：

```text
P001_servo_mouth.csv
```

它把：

```text
start_viseme / end_viseme / alpha
```

转换成：

```text
mouth_open
corner_l
corner_r
upper_lip_l
upper_lip_r
lower_lip
```

### 9.2 输入

```text
neutral_viseme_pose_final.csv
P001_viseme_mix.csv
```

### 9.3 插值公式

对每一帧：

```text
servo(t) = (1 - alpha) * servo[start_viseme]
         + alpha * servo[end_viseme]
```

对 6 个嘴部舵机分别计算。

### 9.4 示例

如果：

```text
V0 mouth_open = 0.05
V7 mouth_open = 0.85
alpha = 0.50
```

则：

```text
mouth_open = 0.5 * 0.05 + 0.5 * 0.85 = 0.45
```

其他舵机也一样插值。

### 9.5 输出文件

```text
dataset/P001/P001_servo_mouth.csv
```

| frame_id | time_ms | syllable | start_v | end_v | alpha | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip |
| --------:| -------:| -------- | -------:| -----:| -----:| ----------:| --------:| --------:| -----------:| -----------:| ---------:|
| 5        | 200     | da       | 2       | 7     | 0.00  |            |          |          |             |             |           |
| 6        | 240     | da       | 2       | 7     | 0.20  |            |          |          |             |             |           |

### 9.6 注意事项

```text
mouth_open 必须保持在 [0,1]
其他舵机必须保持在各自安全范围内
不同舵机可以单位不同，但同一个舵机内部可以插值
```

---

## 10. 阶段十：补全 16 路舵机轨迹并处理静音段

### 10.1 阶段目标

阶段十要得到：

```text
P001_servo_target_16ch.csv
```

### 10.2 补全规则

```text
0–7：眉毛、眼皮、眼球 = neutral_rest
8–13：嘴部 = P001_servo_mouth.csv
14–15：脸颊 = neutral_rest
```

### 10.3 输出文件格式

| frame_id | time_ms | brow_head_l | brow_head_r | eyelid_open_l | eyelid_open_r | eye_h_attention_l | eye_h_attention_r | eye_v_attention_l | eye_v_attention_r | mouth_open | mouth_up_corner_l | mouth_up_corner_r | mouth_lip_upper_l | mouth_lip_upper_r | mouth_lip_lower | cheek_l | cheek_r |
| --------:| -------:| -----------:| -----------:| -------------:| -------------:| -----------------:| -----------------:| -----------------:| -----------------:| ----------:| -----------------:| -----------------:| -----------------:| -----------------:| ---------------:| -------:| -------:|

### 10.4 静音段处理

对于 active=0 的帧，不要一直保持上一个嘴型。

建议规则：

| 停顿长度       | 处理方式                     |
| ----------:| ------------------------ |
| < 120 ms   | 不完全回 neutral，保持上一嘴型并轻微过渡 |
| 120–400 ms | 用 2–4 帧平滑回 neutral       |
| > 400 ms   | 回 neutral 并保持            |

### 10.5 为什么要处理静音段

如果不处理，机器人可能在停顿时保持张嘴状态。

如果每个短停顿都马上闭嘴，又会显得机械。

所以要根据停顿长度做不同处理。

---

## 11. 阶段十一：舵机安全裁剪和平滑

### 11.1 阶段目标

保证生成的 16 路舵机目标值安全、连续、不跳变。

### 11.2 准备 servo_limits.csv

```text
dataset/00_calibration/servo_limits.csv
```

示例：

| servo_name        | min | max |
| ----------------- | ---:| ---:|
| mouth_open        | 0.0 | 1.0 |
| mouth_up_corner_l |     |     |
| mouth_up_corner_r |     |     |
| mouth_lip_upper_l |     |     |
| mouth_lip_upper_r |     |     |
| mouth_lip_lower   |     |     |

### 11.3 clamp

对每个值做：

```text
value = clamp(value, min, max)
```

### 11.4 最大速度限制

防止每帧变化过大：

```text
delta = current - previous

if abs(delta) > max_delta:
    current = previous + sign(delta) * max_delta
```

建议初始值：

```text
mouth_open 每帧最大变化：0.10–0.15
其他角度类舵机每帧最大变化：根据实际舵机速度设定
```

### 11.5 低通滤波

可选：

```text
smoothed[t] = beta * target[t] + (1 - beta) * smoothed[t-1]
```

建议：

```text
beta = 0.6 ~ 0.8
```

### 11.6 输出文件

可以覆盖或另存为：

```text
P001_servo_target_16ch_safe.csv
```

---

## 12. 阶段十二：机器人执行与日志采集

### 12.1 阶段目标

播放整段音频，同时按时间发送舵机轨迹，并录制视频。

输入：

```text
P001.wav
P001_servo_target_16ch_safe.csv
```

输出：

```text
P001_execution_log.csv
P001_robot.mp4
```

### 12.2 执行流程

```text
机器人回 neutral_rest
    ↓
开始摄像头录像
    ↓
播放 P001.wav
    ↓
按 time_ms 发送每帧 16 路舵机目标
    ↓
保存执行日志
    ↓
停止录像
```

### 12.3 同步伪代码

```python
start_time = now()
play_audio("P001.wav")

for row in servo_target:
    target_time = start_time + (row["time_ms"] + servo_audio_offset_ms) / 1000.0

    while now() < target_time:
        sleep(0.001)

    send_servo_command(row)
    log_send_time(row)
```

### 12.4 全局延迟参数

```text
servo_audio_offset_ms
```

如果嘴型偏早：

```text
servo_audio_offset_ms += 40 或 80
```

如果嘴型偏晚：

```text
servo_audio_offset_ms -= 40 或 80
```

### 12.5 执行日志格式

```text
dataset/P001/P001_execution_log.csv
```

| time_ms | audio_time_ms | frame_id | mouth_open_target | corner_l_target | corner_r_target | upper_lip_l_target | upper_lip_r_target | lower_lip_target | send_success |
| -------:| -------------:| --------:| -----------------:| ---------------:| ---------------:| ------------------:| ------------------:| ----------------:| ------------:|

如果舵机有反馈，加 actual：

```text
mouth_open_actual
corner_l_actual
...
```

### 12.6 录制视频

```text
dataset/P001/P001_robot.mp4
```

建议：

```text
正面固定拍摄
30 fps 或 60 fps
固定光照
固定摄像头位置
```

---

## 13. 阶段十三：人工评价与问题记录

### 13.1 阶段目标

对机器人执行视频进行评分，记录问题，指导下一轮修改。

输出：

```text
human_rating.csv
issue_log.csv
```

### 13.2 评分表

```text
dataset/P001/human_rating.csv
```

| paragraph_id | rater_id | lip_sync_score | viseme_clarity_score | naturalness_score | overall_score | comment |
| ------------ | -------- | --------------:| --------------------:| -----------------:| -------------:| ------- |
| P001         | R1       |                |                      |                   |               |         |
| P001         | R2       |                |                      |                   |               |         |

评分：

| 分数  | 含义    |
| ---:| ----- |
| 1   | 很差    |
| 2   | 较差    |
| 3   | 基本可接受 |
| 4   | 较好    |
| 5   | 很好    |

### 13.3 问题记录表

```text
dataset/P001/issue_log.csv
```

| paragraph_id | time_ms | syllable | issue_type            | description | suggested_fix_stage |
| ------------ | -------:| -------- | --------------------- | ----------- | ------------------- |
| P001         |         | ba       | no_lip_closure        | b 没有明显闭唇    | stage_2             |
| P001         |         | a        | mouth_not_open_enough | a 开口不够大     | stage_2             |
| P001         |         | all      | mouth_too_late        | 嘴型整体偏晚      | stage_12_offset     |
| P001         |         | all      | motion_jerky          | 嘴部动作跳变      | stage_8_or_11       |

### 13.4 问题回溯规则

| 问题        | 优先修改阶段                                 |
| --------- | -------------------------------------- |
| b/p/m 不闭唇 | 阶段二：修改 V0                              |
| a 开口不够大   | 阶段二：修改 V7                              |
| i 像笑      | 阶段二：修改 V5                              |
| o/w 不够圆   | 阶段二：修改 V3/V6                           |
| 嘴型整体偏早/偏晚 | 阶段十二：调整 servo_audio_offset_ms          |
| 音节分配不合理   | 阶段六/七：调 RMS threshold 或 allocate_units |
| 嘴型跳变太硬    | 阶段八/十一：smooth alpha 或平滑舵机              |
| 舵机跟不上     | 阶段十一/十二：降低速度、调整 offset                 |

---

## 14. 阶段十四：参数迭代

### 14.1 阶段目标

根据阶段十三的评分和问题记录，回到对应阶段修改参数。

### 14.2 推荐迭代顺序

优先级从高到低：

```text
1. 先修全局同步 offset
2. 再修静态 viseme 表
3. 再修 RMS threshold / active segment
4. 再修 alpha 曲线和平滑
5. 最后再考虑复杂音素对齐和情绪层
```

### 14.3 为什么这样排序

如果整体偏早/偏晚，不要先改 V0/V7，因为问题不是嘴型本身，而是音频和舵机时间对不齐。

如果 b/p/m 不闭唇，不要改 RMS，因为问题是 V0 姿态不好。

如果动作跳变硬，不要改静态表，而是改 alpha 或平滑。

---

## 15. 连续说话的特殊处理

### 15.1 短句和连续段落的区别

短句：

```text
一句话 → 一个 active region → 分配所有音节
```

连续段落：

```text
一段话 → 多个 phrase → 多个 active region → 每个 phrase 内部分配音节
```

### 15.2 不要每句都强制回 neutral

错误做法：

```text
大家好 → 回 neutral → 欢迎来到实验室 → 回 neutral → 今天我们...
```

正确做法：

```text
只有明显停顿时才回 neutral
短停顿保持自然过渡
长停顿回 neutral
```

### 15.3 phrase 与 active segment 对齐

理想情况：

```text
phrase 数量 = active segment 数量
```

则按顺序对齐。

如果不一致，第一版可以退化成：

```text
把整段 active frames 全部合并
对所有音节全局分配
```

后续再做更精细的 forced alignment。

---

## 16. 推荐项目目录结构

```text
viseme_sync/
  config/
    neutral_rest.csv
    neutral_viseme_pose_final.csv
    viseme_meta.csv
    pinyin_to_viseme.json
    servo_limits.csv

  data/
    P001/
      P001_text.txt
      P001_phrase.json
      P001.wav
      P001_pinyin.json
      P001_syllable_viseme.json
      P001_rms.csv
      P001_active_segments.csv
      P001_phrase_segment.csv
      P001_allocation.csv
      P001_viseme_mix.csv
      P001_servo_mouth.csv
      P001_servo_target_16ch.csv
      P001_servo_target_16ch_safe.csv
      P001_execution_log.csv
      P001_robot.mp4
      human_rating.csv
      issue_log.csv

  src/
    text_process.py
    tts.py
    pinyin_convert.py
    viseme_mapper.py
    audio_rms.py
    segment_detect.py
    allocate_units.py
    alpha_mix.py
    servo_trajectory.py
    servo_smoothing.py
    robot_player.py
    evaluation.py
```

---

## 17. 主程序伪代码

```python
def run_paragraph_pipeline(paragraph_id: str, text: str):
    # 阶段四：保存文本与切 phrase
    save_text(paragraph_id, text)
    phrases = split_phrases(text)
    save_json(f"{paragraph_id}_phrase.json", phrases)

    # 阶段四：TTS 生成整段音频
    audio_path = synthesize_tts(text, out=f"{paragraph_id}.wav")

    # 阶段五：转拼音
    phrase_pinyin = convert_phrases_to_pinyin(phrases)
    save_json(f"{paragraph_id}_pinyin.json", phrase_pinyin)

    # 阶段五：拼音转 start/end viseme
    syllable_visemes = map_pinyin_to_visemes(
        phrase_pinyin,
        pinyin_to_viseme_path="config/pinyin_to_viseme.json"
    )
    save_json(f"{paragraph_id}_syllable_viseme.json", syllable_visemes)

    # 阶段六：提取 RMS
    rms_table = extract_rms_envelope(
        audio_path,
        control_hz=25,
        threshold=0.10
    )
    save_csv(f"{paragraph_id}_rms.csv", rms_table)

    # 阶段七：active segment
    segments = detect_active_segments(rms_table)
    save_csv(f"{paragraph_id}_active_segments.csv", segments)

    # 阶段七：phrase 对齐 segment
    phrase_segments = align_phrases_to_segments(phrases, segments)
    save_csv(f"{paragraph_id}_phrase_segment.csv", phrase_segments)

    # 阶段七：分配音节帧
    allocation = allocate_units(
        syllable_visemes,
        phrase_segments
    )
    save_csv(f"{paragraph_id}_allocation.csv", allocation)

    # 阶段八：计算 alpha
    viseme_mix = compute_alpha_mix(allocation, control_hz=25)
    save_csv(f"{paragraph_id}_viseme_mix.csv", viseme_mix)

    # 阶段九：生成嘴部舵机轨迹
    mouth_traj = generate_mouth_trajectory(
        viseme_mix,
        viseme_pose_path="config/neutral_viseme_pose_final.csv"
    )
    save_csv(f"{paragraph_id}_servo_mouth.csv", mouth_traj)

    # 阶段十：补全 16 路
    full_traj = build_16ch_trajectory(
        mouth_traj,
        neutral_rest_path="config/neutral_rest.csv"
    )

    # 阶段十：处理静音段
    full_traj = handle_silence_frames(
        full_traj,
        rms_table,
        neutral_rest_path="config/neutral_rest.csv"
    )

    # 阶段十一：安全裁剪和平滑
    full_traj = clamp_servo_values(
        full_traj,
        limits_path="config/servo_limits.csv"
    )
    full_traj = smooth_trajectory(full_traj)

    save_csv(f"{paragraph_id}_servo_target_16ch_safe.csv", full_traj)

    return audio_path, full_traj
```

机器人执行：

```python
def execute_robot(paragraph_id: str):
    audio_path = f"data/{paragraph_id}/{paragraph_id}.wav"
    servo_path = f"data/{paragraph_id}/{paragraph_id}_servo_target_16ch_safe.csv"

    move_robot_to_neutral("config/neutral_rest.csv")
    start_camera_recording(f"data/{paragraph_id}/{paragraph_id}_robot.mp4")

    play_audio_and_send_servos(
        audio_path=audio_path,
        servo_csv=servo_path,
        control_hz=25,
        servo_audio_offset_ms=0
    )

    stop_camera_recording()
```

---

## 18. 最小可运行版本

第一版只实现这些：

```text
1. 输入一段中文文本
2. TTS 生成整段 wav
3. 文本转拼音
4. 拼音转 start/end viseme
5. 提取 RMS active region
6. active frames 按 phrase / 音节平均分配
7. 音节内部线性 alpha
8. 查表插值生成 6 路嘴部舵机
9. 补全 16 路
10. 播放音频并发送轨迹
11. 录视频
12. 人工评分
```

暂时不要加入：

```text
复杂音素对齐
深度学习模型
情绪表情
眉毛动态
眼球动态
脸颊情绪协同
复杂 coarticulation
```

等中性嘴型同步稳定后，再加情绪层。

---

## 19. 最终一句话总结

这套系统的核心是建立统一时间轴：

```text
音频第 t 帧
    ↓
是否 active
    ↓
属于哪个 phrase
    ↓
属于哪个音节
    ↓
该音节的 start_viseme / end_viseme
    ↓
当前 alpha
    ↓
插值得到 6 路嘴部舵机
    ↓
补全 16 路舵机
    ↓
同步播放与执行
```

只要这个时间轴稳定，你们就可以从单句扩展到连续段落，也可以在后续加入情绪嘴型、眉眼动态和脸颊协同。
