# Squat AI MVP

WiFi phone-camera MVP for real-time squat monitoring.

This project uses an existing phone app as a WiFi camera, receives the stream through MediaMTX, pulls frames with Python, runs pose estimation, evaluates side-view squat mechanics, plays TTS alerts, and saves session data.

## Architecture

```text
Phone App (Larix Broadcaster)
  -> RTMP push over WiFi
  -> MediaMTX local media gateway
  -> RTSP pull by Python
  -> MediaPipe Pose adapter
  -> SquatSideEngine biomechanics rules
  -> AlertPolicy + TTS
  -> OpenCV overlay UI + JSONL session recorder
```

The current perception backend is MediaPipe Pose because it is the fastest path for local testing and gives 33 landmarks including feet. The internal schema is backend-neutral, so RTMPose/RTMW/MMPose can replace it without changing the biomechanics engine.

## Tested target environment

- Python 3.10 or 3.11 recommended
- macOS / Linux / Windows
- Phone and computer on the same WiFi
- Docker optional, only for MediaMTX

## 1. Install Python dependencies

```bash
cd squat_ai_mvp
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

If `pyttsx3` has audio issues on your machine, run with `--tts print` first.

## 2. Start MediaMTX

Using Docker Compose:

```bash
docker compose up -d
```

Check ports:

```bash
curl http://127.0.0.1:9997/v3/config/global/get
```

Stop it:

```bash
docker compose down
```

## 3. Find your computer LAN IP

macOS:

```bash
ipconfig getifaddr en0
```

Linux:

```bash
hostname -I
```

Windows PowerShell:

```powershell
ipconfig
```

Assume the LAN IP is `192.168.1.20` below.

## 4. Configure phone app

Recommended app: Larix Broadcaster on iPhone or Android.

Connection URL:

```text
rtmp://192.168.1.20:1935/live/side
```

Recommended video settings:

```text
Resolution: 1280x720
FPS: 30
Codec: H.264
Bitrate: 2500-4000 kbps
Keyframe interval: 1s
Audio: off
Orientation: landscape fixed
```

Place the phone at side view for squats.

## 5. Run the MVP

```bash
python run.py --config configs/app.yaml
```

The app reads:

```text
rtsp://127.0.0.1:8554/live/side
```

Press `q` in the OpenCV video window to stop.

Run without UI:

```bash
python run.py --config configs/app.yaml --no-ui --tts print
```

Override stream URL:

```bash
python run.py --stream-url rtsp://127.0.0.1:8554/live/side
```

Debug with a local webcam instead of phone:

```bash
python run.py --stream-url 0 --tts print
```

Debug with a video file:

```bash
python run.py --stream-url /path/to/squat.mp4 --tts print
```

## Output data

Each run writes:

```text
sessions/<session_id>_squat/
  session.json
  frames.jsonl
  pose.jsonl
  analysis.jsonl
  reps.jsonl
  faults.jsonl
  alerts.jsonl
  overlay_side.mp4
  report.md
```

Keep these files. They are the basis for rule tuning, model upgrades, and later Agent analysis.

## First-version detection scope

Current MVP supports side-view squat only.

Implemented phases:

```text
setup -> descent -> bottom -> ascent -> lockout
```

Implemented alerts:

- `depth_not_enough`
- `torso_lean_too_much`
- `hip_rise_too_early`

The rule thresholds live in:

```text
rules/squat.side.yaml
```

## Important notes

1. This is not medical advice and is not a substitute for a qualified coach.
2. Side-view only cannot reliably detect knee valgus. Add a front camera for that.
3. Hardlift/deadlift analysis should add barbell detection; the `objects` field is reserved for that.
4. WiFi quality matters. Start with 720p/30fps and do not use 1080p until the full pipeline is stable.
5. If pose points jump, improve lighting, increase phone distance, and keep the full body visible.

## Project layout

```text
squat_ai_mvp/
  core/
    stream/          video source adapters
    perception/      pose backend adapters
    biomechanics/    metrics, phases, rules
    alert/           alert policy and TTS
    session/         JSONL/video/report recording
    ui/              OpenCV overlay UI
configs/app.yaml
rules/squat.side.yaml
deploy/mediamtx.yml
docker-compose.yml
run.py
```
