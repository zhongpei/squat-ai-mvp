from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from squat_ai_mvp.core.alert.tts import AlertCommand
from squat_ai_mvp.core.biomechanics.schemas import AnalysisResult, FaultEvent, PoseFrame, RepEvent
from squat_ai_mvp.core.stream.source import VideoFrame


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.f = path.open("a", encoding="utf-8")

    def write(self, obj: dict[str, Any]) -> None:
        self.f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")

    def close(self) -> None:
        self.f.close()


class SessionRecorder:
    def __init__(
        self,
        save_root: str | Path,
        session_id: str,
        exercise: str,
        save_overlay_video: bool = True,
        save_raw_video: bool = False,
    ) -> None:
        self.root = Path(save_root).resolve() / f"{session_id}_{exercise}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.exercise = exercise
        self.save_overlay_video = save_overlay_video
        self.save_raw_video = save_raw_video
        self.frames = JsonlWriter(self.root / "frames.jsonl")
        self.pose = JsonlWriter(self.root / "pose.jsonl")
        self.analysis = JsonlWriter(self.root / "analysis.jsonl")
        self.reps = JsonlWriter(self.root / "reps.jsonl")
        self.faults = JsonlWriter(self.root / "faults.jsonl")
        self.alerts = JsonlWriter(self.root / "alerts.jsonl")
        self.raw_writer: Optional[cv2.VideoWriter] = None
        self.overlay_writer: Optional[cv2.VideoWriter] = None
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.rep_count = 0
        self.fault_count = 0
        self._write_session_meta()

    def _write_session_meta(self) -> None:
        meta = {
            "session_id": self.session_id,
            "exercise": self.exercise,
            "started_at": self.started_at,
            "schema_version": 1,
        }
        (self.root / "session.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_frame(self, vf: VideoFrame) -> None:
        self.frames.write(vf.event.to_dict())
        if self.save_raw_video:
            self._write_video("raw", vf.image_bgr, vf.event.fps_est or 30.0)

    def record_pose(self, pose: Optional[PoseFrame]) -> None:
        if pose is not None:
            self.pose.write(pose.to_dict())

    def record_analysis(self, result: AnalysisResult) -> None:
        self.analysis.write(result.to_dict())
        if result.rep_event:
            self.rep_count = max(self.rep_count, result.rep_event.rep_id)
            self.reps.write(result.rep_event.to_dict())
        for fault in result.fault_events:
            self.fault_count += 1
            self.faults.write(fault.to_dict())

    def record_alert(self, command: AlertCommand, timestamp_ms: int) -> None:
        self.alerts.write({
            "timestamp_ms": timestamp_ms,
            "text": command.text,
            "priority": command.priority,
            "cooldown_key": command.cooldown_key,
        })

    def record_overlay(self, frame_bgr: np.ndarray, fps: float) -> None:
        if self.save_overlay_video:
            self._write_video("overlay", frame_bgr, fps or 30.0)

    def _write_video(self, kind: str, frame: np.ndarray, fps: float) -> None:
        writer_attr = f"{kind}_writer"
        writer = getattr(self, writer_attr)
        if writer is None:
            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            path = str(self.root / f"{kind}_side.mp4")
            writer = cv2.VideoWriter(path, fourcc, max(10.0, min(60.0, fps)), (w, h))
            setattr(self, writer_attr, writer)
        writer.write(frame)

    def write_report(self) -> None:
        report = f"""# Squat AI MVP Report\n\n- Session: `{self.session_id}`\n- Exercise: `{self.exercise}`\n- Started: {self.started_at}\n- Reps: {self.rep_count}\n- Fault events: {self.fault_count}\n\nFiles:\n\n- `frames.jsonl` raw frame metadata\n- `pose.jsonl` pose landmarks\n- `analysis.jsonl` per-frame metrics and phase\n- `reps.jsonl` rep-level summary\n- `faults.jsonl` detected faults\n- `alerts.jsonl` spoken alerts\n- `overlay_side.mp4` overlay video if enabled\n"""
        (self.root / "report.md").write_text(report, encoding="utf-8")

    def close(self) -> None:
        self.write_report()
        for w in (self.frames, self.pose, self.analysis, self.reps, self.faults, self.alerts):
            w.close()
        if self.raw_writer:
            self.raw_writer.release()
        if self.overlay_writer:
            self.overlay_writer.release()
