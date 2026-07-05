from __future__ import annotations

import argparse
import signal
import time

from squat_ai_mvp.core.alert.policy import AlertPolicy
from squat_ai_mvp.core.alert.tts import AsyncTTS, create_tts_provider
from squat_ai_mvp.core.biomechanics.squat_engine import SquatSideEngine
from squat_ai_mvp.core.config import load_config, load_yaml
from squat_ai_mvp.core.perception.mediapipe_pose import MediaPipePoseEstimator
from squat_ai_mvp.core.session.recorder import SessionRecorder
from squat_ai_mvp.core.stream.source import OpenCVStreamSource
from squat_ai_mvp.core.ui.opencv_view import OpenCVView


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="WiFi phone-camera squat monitoring MVP")
    p.add_argument("--config", default="configs/app.yaml", help="YAML config path")
    p.add_argument(
        "--stream-url",
        default=None,
        help="Override stream.input_url, e.g. rtsp://127.0.0.1:8554/live/side",
    )
    p.add_argument("--no-ui", action="store_true", help="Disable OpenCV UI window")
    p.add_argument(
        "--tts",
        default=None,
        choices=["pyttsx3", "print"],
        help="Override alert.tts_provider",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = load_config(args.config)

    session_id = time.strftime("%Y%m%d_%H%M%S")
    exercise = cfg.session.get("exercise", "squat")
    stream_cfg = dict(cfg.stream)
    if args.stream_url:
        stream_cfg["input_url"] = args.stream_url

    rules_file = cfg.resolve_path(
        cfg.biomechanics.get("rules_file", "rules/squat.side.yaml")
    )
    rules = load_yaml(rules_file)

    print("=" * 72)
    print("Squat AI MVP")
    print(f"Session: {session_id}")
    print(f"Exercise: {exercise}")
    print(f"Input:   {stream_cfg.get('input_url')}")
    print("Phone push URL example: rtmp://<computer_lan_ip>:1935/live/side")
    print("Press 'q' in the video window to quit.")
    print("=" * 72)

    source = OpenCVStreamSource(
        input_url=str(stream_cfg.get("input_url")),
        session_id=session_id,
        camera_id=str(stream_cfg.get("camera_id", "side_phone_1")),
        camera_role=str(stream_cfg.get("camera_role", "side")),
        expected_fps=float(stream_cfg.get("expected_fps", 30)),
        reconnect=bool(stream_cfg.get("reconnect", True)),
        reconnect_interval_sec=float(stream_cfg.get("reconnect_interval_sec", 2.0)),
        buffer_size=int(stream_cfg.get("buffer_size", 1)),
        rotate=int(stream_cfg.get("rotate", 0)),
        mirror=bool(stream_cfg.get("mirror", False)),
        max_width=stream_cfg.get("max_width", 1280),
    )

    perception_cfg = cfg.perception
    pose = MediaPipePoseEstimator(
        model_complexity=int(perception_cfg.get("model_complexity", 1)),
        min_detection_confidence=float(
            perception_cfg.get("min_detection_confidence", 0.55)
        ),
        min_tracking_confidence=float(
            perception_cfg.get("min_tracking_confidence", 0.55)
        ),
        min_keypoint_score=float(perception_cfg.get("min_keypoint_score", 0.45)),
    )

    engine = SquatSideEngine(
        rules=rules,
        smoothing_window=int(cfg.biomechanics.get("smoothing_window", 5)),
        min_rep_duration_ms=int(cfg.biomechanics.get("min_rep_duration_ms", 700)),
    )

    alert_cfg = cfg.alert
    policy = AlertPolicy(
        enabled=bool(alert_cfg.get("enabled", True)),
        same_fault_cooldown_ms=int(alert_cfg.get("same_fault_cooldown_ms", 2500)),
        max_alerts_per_rep=int(alert_cfg.get("max_alerts_per_rep", 2)),
        max_alerts_per_set=int(alert_cfg.get("max_alerts_per_set", 30)),
    )
    tts_provider = args.tts or str(alert_cfg.get("tts_provider", "pyttsx3"))
    tts = AsyncTTS(
        create_tts_provider(
            tts_provider,
            rate=int(alert_cfg.get("voice_rate", 185)),
            volume=float(alert_cfg.get("voice_volume", 1.0)),
        )
    )

    recorder = SessionRecorder(
        save_root=cfg.resolve_path(cfg.session.get("save_dir", "sessions")),
        session_id=session_id,
        exercise=exercise,
        save_overlay_video=bool(cfg.session.get("save_overlay_video", True)),
        save_raw_video=bool(cfg.session.get("save_raw_video", False)),
    )

    ui_enabled = bool(cfg.ui.get("enabled", True)) and not args.no_ui
    view = (
        OpenCVView(
            window_name=str(cfg.ui.get("window_name", "Squat AI MVP")),
            draw_skeleton=bool(cfg.ui.get("draw_skeleton", True)),
            draw_metrics=bool(cfg.ui.get("draw_metrics", True)),
        )
        if ui_enabled
        else None
    )
    quit_key = str(cfg.ui.get("quit_key", "q"))

    stop = False

    def handle_sigint(signum, frame):  # noqa: ANN001
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        for vf in source.frames():
            if stop:
                break
            recorder.record_frame(vf)
            pose_frame = pose.infer(vf)
            recorder.record_pose(pose_frame)
            result = engine.analyze(pose_frame)
            recorder.record_analysis(result)

            for cmd in policy.filter_faults(result.fault_events):
                print(f"[alert] {cmd.text}")
                tts.speak(cmd.text)
                recorder.record_alert(cmd, vf.event.timestamp_ms)

            if view is not None:
                overlay = view.render(vf.image_bgr, pose_frame, result)
                recorder.record_overlay(
                    overlay,
                    vf.event.fps_est or float(stream_cfg.get("expected_fps", 30)),
                )
                key = view.show(overlay)
                if key == ord(quit_key):
                    break
    finally:
        print("[shutdown] Closing resources...")
        source.close()
        pose.close()
        tts.close()
        recorder.close()
        if view is not None:
            view.close()
        print(f"[done] Session saved to: {recorder.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
