确定：**第一版就用手机 WiFi 推流，不走 USB，不走虚拟摄像头。**

最终设计我建议定为：

```text id="nos5dc"
手机现有 App
→ WiFi 推 RTMP/SRT
→ 本机 MediaMTX 流媒体网关
→ Video Ingest 解码成帧
→ Pose / Object Perception
→ Biomechanics Engine
→ Alert Engine + TTS
→ UI + Session Store + Report
```

核心结论：**第一版使用 Larix Broadcaster + MediaMTX + Python 本地分析。**

Larix Broadcaster 支持 iOS 和 Android，并支持 SRT、RTMP、NDI、WebRTC、RTSP、Zixi、RIST 等多种推流协议；MediaMTX 是一个零依赖实时媒体服务器，支持发布/读取 RTSP、RTMP、SRT、WebRTC、HLS 等，并可在协议之间自动转换。([Softvelum][1]) ([GitHub][2])

---

## 1. MVP 第一版的手机输入方案

### 推荐主路径：RTMP Push

```text id="y9wzri"
手机 Larix Broadcaster
→ rtmp://<电脑IP>:1935/live/side
→ MediaMTX
→ rtsp://127.0.0.1:8554/live/side
→ Video Ingest
```

为什么第一版用 RTMP：

| 方案              | 判断                                               |
| --------------- | ------------------------------------------------ |
| RTMP            | 第一版最稳，手机 App 支持好，MediaMTX 支持好，FFmpeg/OpenCV 拉流简单 |
| SRT             | 延迟和弱网更好，但配置比 RTMP 稍复杂，作为第一版可选                    |
| RTSP 手机直推       | 可用，但手机 App 支持和兼容性不如 RTMP 稳                       |
| WebRTC          | 延迟最低方向之一，但信令、浏览器权限、服务端集成复杂，第一版不建议作为主链路           |
| MJPEG/IP Webcam | Android 调试可以，iPhone 生态差，不适合作为跨平台主方案              |

所以 MVP 标准输入定为：

```text id="d61k6g"
RTMP as primary ingest
SRT as reserved ingest
RTSP/WebRTC as output/preview path
```

---

## 2. 第一版部署拓扑

假设电脑和手机在同一个 WiFi。

```text id="bgjvxe"
[Phone]
  Larix Broadcaster
  URL: rtmp://192.168.1.20:1935/live/side
  720p / 30fps / H.264 / 2-4 Mbps

        ↓ WiFi

[Computer]
  MediaMTX
    RTMP ingest :1935
    RTSP output :8554
    WebRTC preview :8889
    Metrics/API optional

        ↓ local pull

  squat-ai-mvp
    video_ingest
    perception
    biomechanics
    alert
    ui
    session_store
```

MediaMTX 本身支持把流发布到服务端、从服务端读取、协议转换、多 stream path、录制、Prometheus metrics、hook 等能力，这正适合做你的流媒体网关，而不是自己写 RTMP/RTSP 服务器。([GitHub][2])

---

## 3. 服务边界

第一版即使是本地程序，也按服务边界设计。可以先跑在一个 Python 进程里，但代码结构必须按模块隔离。

```text id="te5ybg"
mvp/
  app/
    desktop_ui/
    main.py

  core/
    stream/
      source.py
      mediamtx_source.py
      video_file_source.py
      frame_bus.py

    perception/
      pose_model.py
      rtmpose_adapter.py
      object_detector.py

    biomechanics/
      engine.py
      phase_state_machine.py
      metrics.py
      rules.py

    alert/
      policy.py
      tts.py

    session/
      recorder.py
      schema.py
      report.py

  rules/
    squat.side.yaml
    deadlift.side.yaml
    split_squat.front.yaml

  configs/
    app.yaml
    mediamtx.yml
```

第一版功能可以只做深蹲，但目录和接口必须支持后面扩展硬拉、单腿蹲、双摄像头、杠铃检测。

---

## 4. 流媒体接入层设计

### 4.1 MediaMTX 作为唯一入口

不要让分析程序直接面对各种手机 App。

统一抽象：

```text id="wh48z3"
Phone App
→ MediaMTX
→ StreamSource
→ Frame
```

这样后面你换 Larix、换 Android IP Camera、换 WebRTC、换 RTSP 摄像头，都不影响动作分析核心。

### 4.2 Stream path 规范

第一版单摄像头：

```text id="ewy4qd"
/live/side
```

后续双摄像头：

```text id="yrw9s9"
/live/side
/live/front
```

后续多用户/多 session：

```text id="7htm9y"
/sessions/{session_id}/side
/sessions/{session_id}/front
```

第一版先不要做多用户，但 path 规则一开始就这样设计。

---

## 5. 手机端配置标准

### Larix Broadcaster 推荐设置

```text id="0y7fg5"
Connection:
  URL: rtmp://<电脑局域网IP>:1935/live/side

Video:
  Resolution: 1280x720
  FPS: 30
  Codec: H.264
  Bitrate: 2500-4000 kbps
  Keyframe interval: 1s
  Orientation: 横屏固定

Audio:
  可关
```

为什么 720p/30fps：

```text id="vllnbx"
720p 足够做人体姿态；
30fps 足够做深蹲/硬拉动作阶段；
码率 2.5-4Mbps 在普通 WiFi 下稳定；
第一版不要上 1080p，解码和模型开销更高。
```

Larix 支持横竖屏、前后摄像头切换、内容录制、截图、RTMP/SRT/RTSP/WebRTC 等能力，所以第一版不用开发手机 App。([Softvelum][1])

---

## 6. 本机服务设计

### 6.1 stream-gateway：MediaMTX

职责：

```text id="n5o94o"
1. 接收手机 RTMP/SRT 推流
2. 转成分析端容易读取的 RTSP
3. 提供 WebRTC/HLS 预览
4. 支持后续多摄像头 path
5. 支持录制和 metrics
```

MVP 启动方式：

```bash id="x1373z"
docker run --rm -it \
  --name mediamtx \
  --network host \
  bluenviron/mediamtx:latest
```

如果不用 Docker，也可以直接下载单文件运行。MediaMTX 的一个优点就是单可执行文件、跨 Linux/Windows/macOS，适合本地工具。([GitHub][2])

---

### 6.2 video_ingest

输入：

```text id="3e6zlu"
rtsp://127.0.0.1:8554/live/side
```

职责：

```text id="e6wca7"
1. 拉流
2. 解码
3. 给每帧打 timestamp
4. 降采样/裁剪/旋转校正
5. 输出 FrameEvent
6. 同时写原始视频缓存
```

输出统一结构：

```json id="gizcww"
{
  "session_id": "20260705_001",
  "camera_id": "side_phone_1",
  "camera_role": "side",
  "frame_id": 1248,
  "timestamp_ms": 41600,
  "source_timestamp_ms": null,
  "width": 1280,
  "height": 720,
  "fps_est": 29.8,
  "image_ref": "memory://frame/1248"
}
```

注意：第一版可以使用服务端接收时间作为 timestamp。以后双摄像头再做 NTP/SEI/帧对齐。Larix 有 SEI time metadata with NTP server 的能力，但这是后续多摄像头精确同步时再启用。([Softvelum][1])

---

### 6.3 perception

职责只做“看见”，不做“判断”。

第一版：

```text id="t7ci10"
FrameEvent
→ RTMPose / RTMW
→ PoseFrame
```

输出：

```json id="fimclm"
{
  "frame_id": 1248,
  "camera_role": "side",
  "person": {
    "keypoints_2d": [],
    "scores": [],
    "bbox": [320, 80, 710, 700]
  },
  "objects": {
    "barbell": null,
    "plates": []
  }
}
```

第一版可以不做杠铃检测，但 `objects` 字段必须保留。硬拉一定会用到。

---

### 6.4 biomechanics

这是核心资产。

输入：

```text id="5v9pvt"
PoseFrame[]
```

处理流程：

```text id="fy6hx0"
keypoint smoothing
→ rep segmentation
→ phase state machine
→ metric extraction
→ fault rule evaluation
```

第一版深蹲侧面阶段：

```text id="q155zw"
setup
descent
bottom
ascent
lockout
```

第一版深蹲指标：

```text id="bj0tg6"
knee_angle
hip_angle
torso_angle
depth_proxy
hip_knee_sync
vertical_stability
```

第一版错误：

```text id="srbsww"
depth_not_enough
torso_lean_too_much
hip_rise_too_early
bottom_unstable
```

输出事件：

```json id="99vz9q"
{
  "type": "fault",
  "exercise": "squat",
  "rep_id": 4,
  "phase": "ascent",
  "code": "hip_rise_too_early",
  "severity": "medium",
  "confidence": 0.81,
  "start_ms": 28420,
  "end_ms": 28980,
  "message": "上升时髋部先起，保持胸部和髋部同步上升",
  "evidence": {
    "hip_velocity": 0.43,
    "knee_velocity": 0.19,
    "torso_angle_delta": 8.7
  }
}
```

---

### 6.5 alert

不要在 biomechanics 里直接 TTS。

```text id="d8h8el"
FaultEvent
→ AlertPolicy
→ AlertCommand
→ TTS
```

策略：

```yaml id="ww2h67"
alert:
  min_fault_duration_ms: 300
  same_fault_cooldown_ms: 2500
  max_alerts_per_rep: 2
  max_alerts_per_set: 10
  allow_interrupt: false
```

输出：

```json id="7h849c"
{
  "type": "tts",
  "priority": "medium",
  "text": "上升时髋部先起，保持胸部和髋部同步上升",
  "cooldown_key": "squat.hip_rise_too_early"
}
```

MVP TTS 可以先用系统 TTS。后面换 edge-tts、OpenAI TTS、本地 TTS，都不影响核心。

---

## 7. UI 设计

第一版不建议直接做 WebUI。你现在的关键是实时动作分析和低延迟闭环，桌面 UI 更稳。

```text id="qzf5lz"
PySide6 / PyQt6 Desktop UI
```

UI 只负责：

```text id="u2y5xb"
1. 显示视频流
2. 显示骨架 overlay
3. 显示当前动作阶段
4. 显示 rep 计数
5. 显示最近错误
6. 开始/停止 session
7. 显示手机推流地址和二维码
```

关键交互：

```text id="yukv5p"
启动 App
→ 显示 rtmp://192.168.1.20:1935/live/side
→ 用户在 Larix 填入 URL
→ 手机开始推流
→ UI 检测到 /live/side 在线
→ 用户点击 Start Session
→ 开始分析
```

---

## 8. Session Store：第一版必须保存数据

每次训练保存：

```text id="tde44n"
sessions/20260705_001_squat/
  session.json
  raw_side.mp4
  overlay_side.mp4
  frames.jsonl
  pose.jsonl
  reps.jsonl
  faults.jsonl
  alerts.jsonl
  report.md
```

其中 `pose.jsonl`、`reps.jsonl`、`faults.jsonl` 必须保存。否则后面无法调规则、做模型训练、做复盘。

---

## 9. 配置文件设计

### app.yaml

```yaml id="gdephf"
session:
  exercise: squat
  mode: live
  save_dir: ./sessions

streams:
  - camera_id: side_phone_1
    role: side
    input_url: rtsp://127.0.0.1:8554/live/side
    expected_fps: 30
    expected_width: 1280
    expected_height: 720

perception:
  pose_model: rtmpose
  device: cuda
  inference_fps: 20
  min_keypoint_score: 0.45

biomechanics:
  rules_file: rules/squat.side.yaml
  smoothing_window: 5

alert:
  enabled: true
  tts_provider: system
  min_fault_duration_ms: 300
  same_fault_cooldown_ms: 2500
```

### rules/squat.side.yaml

```yaml id="b5b8sl"
exercise: squat
view: side

phases:
  - setup
  - descent
  - bottom
  - ascent
  - lockout

metrics:
  knee_angle:
    points: [hip, knee, ankle]
  hip_angle:
    points: [shoulder, hip, knee]
  torso_angle:
    reference: vertical
  depth_proxy:
    expression: hip_y_vs_knee_y
  hip_knee_sync:
    expression: hip_velocity_vs_knee_velocity

faults:
  depth_not_enough:
    phase: bottom
    condition: depth_proxy < 0
    severity: medium
    duration_ms: 200
    message: "深蹲深度不够，继续下到髋部低于膝盖附近"

  torso_lean_too_much:
    phase: descent|bottom|ascent
    condition: torso_angle > 45
    severity: medium
    duration_ms: 300
    message: "身体前倾过多，保持胸部稳定"

  hip_rise_too_early:
    phase: ascent
    condition: hip_knee_sync > 0.35
    severity: high
    duration_ms: 250
    message: "上升时髋部先起，保持胸部和髋部同步上升"
```

---

## 10. 第一版验收标准

第一版不要泛泛说“能识别深蹲”。验收标准应该是工程化的：

```text id="k8v21k"
1. 手机通过 WiFi 成功推 RTMP 到电脑
2. MediaMTX 能稳定接收 /live/side
3. Video Ingest 能以 ≥25fps 解码帧
4. Pose 推理能稳定输出关键点
5. UI 能显示实时视频 + 骨架
6. 深蹲能分出 descent/bottom/ascent/lockout
7. rep 计数误差 ≤ 1 次 / 20 次
8. 至少 3 类错误能触发 TTS
9. 报警延迟 < 800ms
10. 每组训练完整保存 JSONL + report.md
```

---

## 11. 第一版不做的东西

为了避免 MVP 发散，第一版明确不做：

```text id="n77hea"
1. 不开发手机 App
2. 不做账号系统
3. 不做云端
4. 不做多人训练
5. 不做 WebRTC 主链路
6. 不做双摄像头同步
7. 不做 VLM 直接动作判定
8. 不做复杂训练计划
9. 不做硬拉杠铃检测
```

但接口必须预留：

```text id="b32l59"
1. 多 camera_role
2. objects.barbell
3. session_id
4. stream path
5. rules per exercise
6. Agent/report 层
```

---

## 12. 最终方案一句话

**第一版用 Larix Broadcaster 在手机上通过 WiFi 推 RTMP 到本机 MediaMTX；电脑端从 MediaMTX 拉 RTSP 流，进入统一 VideoSourceAdapter，再跑姿态估计、运动学规则、TTS 报警和训练数据保存。**

这个方案是最短路径，但不是短视架构。后面扩展双手机、SRT、RTSP 摄像头、WebRTC、硬拉杠铃检测、Agent 复盘，都不会推倒核心。

[1]: https://softvelum.com/larix/ "Larix Broadcaster – Softvelum: efficient tools to build your streaming networks"
[2]: https://github.com/bluenviron/mediamtx "GitHub - bluenviron/mediamtx: Ready-to-use Media-over-QUIC / SRT / WebRTC / RTSP / RTMP / LL-HLS / MPEG-TS / RTP live media server and media proxy that allows to read, publish, proxy, record and playback real-time video and audio streams. · GitHub"

