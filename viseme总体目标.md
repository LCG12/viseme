# 0. 最终要得到哪些数据文件

建议最终数据集包含这些文件：

```
dataset/  00_calibration/    neutral_rest.csv    servo_limits.csv  01_static_viseme/    neutral_viseme_pose_raw.csv    neutral_viseme_pose_final.csv    viseme_meta.csv  02_audio_corpus/    sentence_dataset.csv    wav/      S001.wav      S002.wav  03_text_to_viseme/    S001_pinyin.json    S001_syllable_viseme.json  04_rms_envelope/    S001_rms.csv  05_allocation/    S001_allocation.csv  06_frame_trajectory/    S001_viseme_mix.csv    S001_servo_target.csv  07_robot_execution/    servo_logs/      S001_execution_log.csv    videos/      S001_robot.mp4  08_evaluation/    human_rating.csv    issue_log.csv
```

其中最核心的不是某一个音节的固定动作，而是：

```
音频帧 → 当前 syllable → start_viseme/end_viseme → alpha → 6 个嘴部舵机目标值
```

---

# 1. 阶段一：采集机器人中性基准姿态

## 1.1 目的

先确定机器人不说话时的自然中性脸。后面所有嘴型都基于这个姿态变化。

## 1.2 操作

让机器人进入：

```
自然闭嘴嘴角不笑、不下垂眉毛放松眼皮自然打开眼球看正前方脸颊不抬
```

记录 16 个舵机角度。

## 1.3 保存文件：`neutral_rest.csv`

| servo_id | servo_name        | angle |
| -------- | ----------------- | ----- |
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

---

# 2. 阶段二：采集 8 个静态 viseme 嘴型

## 2.1 目的

建立这张表：

| viseme_id | 代表音                | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip |
| --------- | ------------------ | ---------- | -------- | -------- | ----------- | ----------- | --------- |
| 0         | b,p,m              |            |          |          |             |             |           |
| 1         | f                  |            |          |          |             |             |           |
| 2         | d,t,n,l,zh,ch,sh,r |            |          |          |             |             |           |
| 3         | w,u                |            |          |          |             |             |           |
| 4         | e,en,eng,k,g,h     |            |          |          |             |             |           |
| 5         | i,j,q,x,z,c,s      |            |          |          |             |             |           |
| 6         | o,ong              |            |          |          |             |             |           |
| 7         | a,an,ang           |            |          |          |             |             |           |

论文中 Table I 也是把中文音素压缩成 8 类基础 viseme，你们这张表就是把这 8 类 viseme 转换成机器人 6 个嘴部舵机姿态。

## 2.2 采集方式

只调 6 个嘴部舵机：

```
8  mouth_open9  mouth_up_corner_l10 mouth_up_corner_r11 mouth_lip_upper_l12 mouth_lip_upper_r13 mouth_lip_lower
```

其他舵机保持 `neutral_rest`。

每个 viseme 人工调 3–5 次，每次保存一次。

## 2.3 保存文件：`neutral_viseme_pose_raw.csv`

| sample_id | viseme_id | trial | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip | video_file | notes |
| --------- | --------- | ----- | ---------- | -------- | -------- | ----------- | ----------- | --------- | ---------- | ----- |
| V0_T1     | 0         | 1     |            |          |          |             |             |           | V0_T1.mp4  | 闭唇    |
| V0_T2     | 0         | 2     |            |          |          |             |             |           | V0_T2.mp4  |       |
| V7_T1     | 7         | 1     |            |          |          |             |             |           | V7_T1.mp4  | 大开口   |

然后从每个 viseme 的多次 trial 中选最自然的一组，生成：

```
neutral_viseme_pose_final.csv
```

---

# 3. 阶段三：为每个 viseme 标注元信息

## 3.1 目的

后面生成连续嘴型时，需要知道每个 viseme 的开口度、形状类别和代表音。

## 3.2 保存文件：`viseme_meta.csv`

| viseme_id | phonemes           | aperture | shape_label       |
| --------- | ------------------ | -------- | ----------------- |
| 0         | b,p,m              | 0        | closed_lip        |
| 1         | f                  | 1        | small_labiodental |
| 2         | d,t,n,l,zh,ch,sh,r | 1        | small_open        |
| 3         | w,u                | 1        | small_round       |
| 4         | e,en,eng,k,g,h     | 3        | mid_open          |
| 5         | i,j,q,x,z,c,s      | 2        | wide_flat         |
| 6         | o,ong              | 4        | round_open        |
| 7         | a,an,ang           | 5        | large_open        |

这里的 `aperture` 不是论文原始编号，而是你们自己定义的“开口度”。后面判断嘴型过渡时，最好用 aperture，而不是直接比较 viseme_id。

---

# 4. 阶段四：采集句子音频数据

## 4.1 目的

既然时间分配由 RMS 包络决定，就要收集句子级音频，而不是收固定音节时长。

## 4.2 准备 30–50 条短句

第一批句子要覆盖所有 viseme：

```
爸爸妈妈你好我是机器人我喜欢学习今天天气很好请问你叫什么名字欢迎来到实验室我们一起说话他说普通话很好小机器人会回答问题
```

## 4.3 每句话保存

| sentence_id | text  | pinyin           | audio_file | duration_ms | speaker | notes |
| ----------- | ----- | ---------------- | ---------- | ----------- | ------- | ----- |
| S001        | 爸爸妈妈  | ba ba ma ma      | S001.wav   |             | tts     |       |
| S002        | 我是机器人 | wo shi ji qi ren | S002.wav   |             | tts     |       |

文件名：

```
02_audio_corpus/sentence_dataset.csv02_audio_corpus/wav/S001.wav
```

建议第一版用 TTS，因为文本、拼音、音频可控。后面再加真人语音。

---

# 5. 阶段五：文本转拼音，再转首末 viseme

## 5.1 目的

每个音节不再对应一个固定动作，而是对应：

```
start_viseme → end_viseme
```

例如：

```
ba = b + a → V0 → V7ma = m + a → V0 → V7wa = w + a → V3 → V7shi = sh + i → V2 → V5wo = w + o → V3 → V6yi = i → V5 → V5
```

## 5.2 保存文件：`S001_syllable_viseme.json`

例如“爸爸妈妈”：

```
{  "sentence_id": "S001",  "text": "爸爸妈妈",  "pinyin": ["ba", "ba", "ma", "ma"],  "syllables": [    {      "idx": 0,      "syllable": "ba",      "initial": "b",      "final": "a",      "start_viseme": 0,      "end_viseme": 7    },    {      "idx": 1,      "syllable": "ba",      "initial": "b",      "final": "a",      "start_viseme": 0,      "end_viseme": 7    },    {      "idx": 2,      "syllable": "ma",      "initial": "m",      "final": "a",      "start_viseme": 0,      "end_viseme": 7    },    {      "idx": 3,      "syllable": "ma",      "initial": "m",      "final": "a",      "start_viseme": 0,      "end_viseme": 7    }  ]}
```

注意：这里仍然没有人工写 `start_hold_ms`、`transition_ms`、`end_hold_ms`。

---

# 6. 阶段六：提取 RMS 能量包络

## 6.1 目的

用音频本身决定有效发声区域。

你们当前 `allocate_units` 用 RMS active region 切分音节帧数，本质上就是：

```
先找出语音中真正有声的帧再把这些 active frames 分给拼音音节
```

## 6.2 操作

对每个 wav 文件提取 RMS。

建议控制频率：

```
25 Hz
```

也就是：

```
每 40 ms 一帧
```

如果音频是 2 秒，就有大约 50 帧。

## 6.3 保存文件：`S001_rms.csv`

| frame_id | time_ms | rms | rms_norm | active |
| -------- | ------- | --- | -------- | ------ |
| 0        | 0       |     |          | 0      |
| 1        | 40      |     |          | 1      |
| 2        | 80      |     |          | 1      |
| 3        | 120     |     |          | 1      |

`active` 可以由阈值产生，例如：

```
active = rms_norm > threshold
```

阈值可以先用经验值，比如 0.05 或 0.1，后面根据实际 TTS 音频调整。

---

# 7. 阶段七：用 active region 自动分配音节帧

## 7.1 目的

把每个音节分配到音频的实际发声区间中。

例如：

```
爸爸妈妈ba ba ma ma
```

如果 RMS active region 是 frame 3 到 frame 34，一共 32 帧，4 个音节，那么可以分配成：

```
ba: frame 3–10ba: frame 11–18ma: frame 19–26ma: frame 27–34
```

如果你们的 `allocate_units` 会根据 RMS 峰值或 active frames 更细地分配，那就直接保存它的输出。

## 7.2 保存文件：`S001_allocation.csv`

| syllable_idx | syllable | start_viseme | end_viseme | start_frame | end_frame | num_frames |
| ------------ | -------- | ------------ | ---------- | ----------- | --------- | ---------- |
| 0            | ba       | 0            | 7          | 3           | 10        | 8          |
| 1            | ba       | 0            | 7          | 11          | 18        | 8          |
| 2            | ma       | 0            | 7          | 19          | 26        | 8          |
| 3            | ma       | 0            | 7          | 27          | 34        | 8          |

这一步是核心：  
**音节的持续时间来自音频 active region，而不是人工预设。**

---

# 8. 阶段八：生成帧级 viseme 混合系数

## 8.1 目的

每个音节内部，根据帧的位置，让 start_viseme 线性过渡到 end_viseme。

比如 `ba`：

```
V0 → V7
```

如果它有 8 帧：

| local_frame | alpha | 含义        |
| ----------- | ----- | --------- |
| 0           | 0.00  | 完全 V0     |
| 1           | 0.14  | V0 多，V7 少 |
| 2           | 0.29  | 继续张开      |
| 3           | 0.43  | 中间        |
| 4           | 0.57  | V7 开始占主导  |
| 5           | 0.71  | 接近 V7     |
| 6           | 0.86  | 接近 V7     |
| 7           | 1.00  | 完全 V7     |

公式：

```
Servo(t) = (1 - alpha) * Servo[start_viseme] + alpha * Servo[end_viseme]
```

## 8.2 保存文件：`S001_viseme_mix.csv`

| frame_id | time_ms | syllable_idx | syllable | start_viseme | end_viseme | alpha |
| -------- | ------- | ------------ | -------- | ------------ | ---------- | ----- |
| 3        | 120     | 0            | ba       | 0            | 7          | 0.00  |
| 4        | 160     | 0            | ba       | 0            | 7          | 0.14  |
| 5        | 200     | 0            | ba       | 0            | 7          | 0.29  |
| 6        | 240     | 0            | ba       | 0            | 7          | 0.43  |

---

# 9. 阶段九：生成帧级舵机目标值

## 9.1 目的

把 `alpha` 和 `neutral_viseme_pose_final.csv` 结合，生成每一帧的 6 个嘴部舵机值。

## 9.2 保存文件：`S001_servo_target.csv`

| frame_id | time_ms | syllable | start_v | end_v | alpha | mouth_open | corner_l | corner_r | upper_lip_l | upper_lip_r | lower_lip |
| -------- | ------- | -------- | ------- | ----- | ----- | ---------- | -------- | -------- | ----------- | ----------- | --------- |
| 3        | 120     | ba       | 0       | 7     | 0.00  |            |          |          |             |             |           |
| 4        | 160     | ba       | 0       | 7     | 0.14  |            |          |          |             |             |           |
| 5        | 200     | ba       | 0       | 7     | 0.29  |            |          |          |             |             |           |

这一份文件就是机器人要执行的目标轨迹。

---

# 10. 阶段十：机器人执行并采集视频

## 10.1 执行内容

播放 `S001.wav`，同时按照 `S001_servo_target.csv` 发送舵机指令。

建议：

```
控制频率：25 Hz每帧间隔：40 ms摄像头：正面固定拍摄视频帧率：30 fps 或 60 fps
```

## 10.2 保存执行日志

保存为：

```
S001_execution_log.csv
```

字段：

| time_ms | audio_time_ms | mouth_open_target | corner_l_target | corner_r_target | upper_lip_l_target | upper_lip_r_target | lower_lip_target |
| ------- | ------------- | ----------------- | --------------- | --------------- | ------------------ | ------------------ | ---------------- |

如果舵机有反馈，再加 actual：

| mouth_open_actual | corner_l_actual | ... |
| ----------------- | --------------- | --- |

## 10.3 保存机器人视频

```
07_robot_execution/videos/S001_robot.mp4
```

---

# 11. 阶段十一：人工评价数据

## 11.1 目的

评价不是为了人工修改每个音节时长，而是为了判断：

```
静态 viseme 姿态是否合理RMS active region 是否切分合理线性混合是否自然机器人舵机是否存在延迟
```

## 11.2 保存文件：`human_rating.csv`

| sentence_id | rater_id | lip_sync_score | clarity_score | naturalness_score | delay_comment | issue_comment |
| ----------- | -------- | -------------- | ------------- | ----------------- | ------------- | ------------- |
| S001        | R1       | 4              | 3             | 4                 | 嘴型略早          | ba 闭唇不够明显     |
| S001        | R2       | 3              | 4             | 3                 | 嘴型略晚          | 张嘴速度慢         |

评分建议：

```
1 = 很差2 = 较差3 = 可接受4 = 较好5 = 很好
```

三个核心指标：

```
lip_sync_score：嘴型和语音是否同步clarity_score：viseme 是否清楚naturalness_score：运动是否自然
```

---

# 12. 阶段十二：问题回溯和参数迭代

根据评价结果，你们不要直接给某个音节写固定时间，而是优先调整以下内容。

## 情况 1：所有句子嘴型整体偏早或偏晚

调整全局延迟：

```
servo_audio_offset_ms
```

例如：

```
嘴型早了 → 舵机轨迹整体延后 40–80 ms嘴型晚了 → 舵机轨迹整体提前 40–80 ms
```

## 情况 2：闭唇音不明显，比如 ba、ma、pa

优先调整：

```
V0 静态姿态
```

也就是让 viseme 0 更接近闭唇。

不要优先改 `ba` 的固定时间。

## 情况 3：a 不够大

调整：

```
V7 静态姿态
```

增大 `mouth_open`，适当调整 upper/lower lip。

## 情况 4：i 像笑

调整：

```
V5 静态姿态
```

让嘴型扁平，但不要嘴角明显上扬。

## 情况 5：RMS 切分不稳定

调整：

```
RMS thresholdactive region smoothingmin_active_framessilence trimming
```

## 情况 6：运动跳变太硬

调整：

```
viseme mixing curveservo smoothingmax_delta_per_frame
```

例如把线性 alpha 改成 smootherstep：

```
alpha_smooth = 3α² - 2α³
```

这样嘴型过渡会更柔和。

---

# 13. 最小可行数据集规模

第一版建议收：

| 数据类型            | 数量         |
| --------------- | ---------- |
| neutral_rest    | 1 组        |
| 8 个 viseme 静态姿态 | 每个 3–5 次   |
| 句子音频            | 30–50 条    |
| RMS 包络          | 每条音频 1 个   |
| allocation 结果   | 每条音频 1 个   |
| servo_target 轨迹 | 每条音频 1 个   |
| 机器人视频           | 每条音频 1 个   |
| 人工评分            | 每条视频 3–5 人 |

第一版不需要收“每个音节固定时长表”。

---

# 14. 整个流程一句话版

完整流程是：

```
标定 neutral rest→ 人工调出 8 个静态 viseme 舵机姿态→ 准备句子文本和音频→ 文本转拼音→ 每个音节映射为 start_viseme/end_viseme→ 提取音频 RMS 包络→ 用 active region 给音节自动分配帧→ 在每个音节内部做 start/end viseme 线性混合→ 生成每帧 6 个嘴部舵机目标值→ 机器人执行并录像→ 人工评价同步性、清晰度、自然度→ 根据问题调整 viseme 姿态、RMS 阈值、全局延迟和平滑参数
```

最关键的修正是：



```
不要收 ba → 固定 start_hold_ms / transition_ms / end_hold_ms
```

而是收：

```
ba 在具体音频 active region 中被分配到的帧+ ba 的 start_viseme/end_viseme+ 每帧 alpha+ 每帧舵机目标值
```

这样才符合你们现在 `allocate_units` 的逻辑。
