# Squat AI MVP

WiFi phone-camera real-time squat monitoring.

Phone pushes RTMP to a local MediaMTX gateway; Python pulls RTSP, runs MediaPipe pose estimation, evaluates side-view squat biomechanics, plays TTS voice alerts, and saves session data.

## Architecture

```text
Phone App (IRL Pro)
  -> RTMP push over WiFi
  -> MediaMTX local media gateway
  -> RTSP pull by Python
  -> MediaPipe Pose (PoseLandmarker, Lite model)
  -> SquatSideEngine phase machine + rules
  -> AlertPolicy + TTS (macOS say / pyttsx3)
  -> OpenCV overlay UI + JSONL session recorder
```

## Requirements

- macOS / Linux / Windows
- Python 3.10 or 3.11
- Docker Desktop (for MediaMTX)
- Phone + computer on same WiFi
- IRL Pro app (iOS)

## Quick start

```bash
make install        # uv venv + sync deps
make docker-up      # start MediaMTX
get IP              # ipconfig getifaddr en0
# configure phone (see below)
make run            # start analysis
```

## 1. Install

```bash
make install
```

If TTS has audio issues, pass `--tts print`.

## 2. Start MediaMTX

```bash
make docker-up
docker compose logs  # verify RTSP/RTMP listeners
```

## 3. Configure IRL Pro (phone)

### Connection

| Field | Value |
|---|---|
| Protocol | RTMP |
| URL | `rtmp://<computer_lan_ip>:1935/live` |
| Stream Key | `side` |

### Video settings

| Setting | Value |
|---|---|
| Resolution | 1280×720 |
| FPS | 30 |
| Codec | H.264 |
| Bitrate | 2500–4000 kbps |
| Keyframe interval | 1s (30 frames) |
| Audio | off |
| Orientation | landscape (fixed) |

Place phone in side view, full body visible, then tap Start/Record.

> IRL Pro combines URL + Stream Key into `rtmp://<ip>:1935/live/side`.

## 4. Run

```bash
make run                     # with UI + TTS
make run ARGS='--tts print --no-ui'   # debug / no audio
make run ARGS='--stream-url 0 --tts print'  # local webcam
```

App reads `rtsp://127.0.0.1:8554/live/side`. Press `q` in the video window to stop.

## Detection scope

**Side-view squat only.**

| Phase | Description |
|---|---|
| setup / lockout | Standing upright |
| descent | Knees bending |
| bottom | Knee at or below target angle |
| ascent | Returning to standing |

| Alert | Trigger |
|---|---|
| `depth_not_enough` | Knee didn't reach bottom, or hip above knee at bottom |
| `torso_lean_too_much` | Torso leans forward beyond threshold |
| `hip_rise_too_early` | Hips rise faster than chest during ascent |

All thresholds in `rules/squat.side.yaml`.

## Output data

```text
sessions/<session_id>_squat/
  session.json          # metadata
  frames.jsonl          # frame events
  pose.jsonl            # pose landmarks
  analysis.jsonl        # per-frame metrics + phase
  reps.jsonl            # completed rep summaries
  faults.jsonl          # detected faults
  alerts.jsonl          # TTS alerts + rep announcements
  overlay_side.mp4      # overlay video (if enabled)
  report.md             # session summary
```

## Project layout

```text
configs/app.yaml          # main config
rules/squat.side.yaml     # squat phase + fault rules
deploy/mediamtx.yml       # MediaMTX config
docker-compose.yml         # MediaMTX container
run.py                     # entry point
squat_ai_mvp/
  main.py                  # pipeline loop
  core/
    stream/source.py       # OpenCV video source
    perception/mediapipe_pose.py  # PoseLandmarker adapter
    biomechanics/          # engine, schemas, math
    alert/                 # policy + TTS providers
    session/recorder.py    # JSONL + video recording
    ui/opencv_view.py      # OpenCV overlay
Makefile                   # uv + test + docker targets
```

## Make targets

| Command | Action |
|---|---|
| `make install` | Create venv + install deps |
| `make test` | Run tests |
| `make dev` | Watch mode (re-run on file change) |
| `make run` | Start analysis |
| `make docker-up` | Start MediaMTX |
| `make docker-down` | Stop MediaMTX |
| `make clean` | Remove venv + caches |

## Notes

1. Not medical advice. Not a substitute for a qualified coach.
2. Side-view only cannot detect knee valgus. Add front camera for that.
3. Start with 720p/30fps. Do not use 1080p until pipeline is stable.
4. If pose landmarks jump, improve lighting and keep full body visible.
5. H.264 decode errors (`decode_slice_header`) are harmless — OpenCV recovers on next I-frame.
