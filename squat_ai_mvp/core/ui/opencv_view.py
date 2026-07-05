from __future__ import annotations

import cv2
import numpy as np

from squat_ai_mvp.core.biomechanics.schemas import AnalysisResult, PoseFrame
from squat_ai_mvp.core.perception.mediapipe_pose import POSE_CONNECTIONS


class OpenCVView:
    def __init__(
        self,
        window_name: str = "Squat AI MVP",
        draw_skeleton: bool = True,
        draw_metrics: bool = True,
    ) -> None:
        self.window_name = window_name
        self.draw_skeleton = draw_skeleton
        self.draw_metrics = draw_metrics
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)

    def render(
        self, image_bgr: np.ndarray, pose: PoseFrame | None, result: AnalysisResult
    ) -> np.ndarray:
        frame = image_bgr.copy()
        if self.draw_skeleton and pose is not None:
            self._draw_skeleton(frame, pose)
        if self.draw_metrics:
            self._draw_metrics(frame, result)
        return frame

    def show(self, image_bgr: np.ndarray) -> int:
        cv2.imshow(self.window_name, image_bgr)
        return cv2.waitKey(1) & 0xFF

    def close(self) -> None:
        cv2.destroyWindow(self.window_name)

    def _draw_skeleton(self, frame: np.ndarray, pose: PoseFrame) -> None:
        for a, b in POSE_CONNECTIONS:
            ka = pose.keypoints.get(a)
            kb = pose.keypoints.get(b)
            if not ka or not kb or ka.score < 0.35 or kb.score < 0.35:
                continue
            cv2.line(
                frame, (int(ka.x), int(ka.y)), (int(kb.x), int(kb.y)), (0, 255, 0), 2
            )
        for kp in pose.keypoints.values():
            if kp.score < 0.35:
                continue
            cv2.circle(frame, (int(kp.x), int(kp.y)), 4, (0, 0, 255), -1)
        if pose.bbox:
            x1, y1, x2, y2 = [int(v) for v in pose.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 128, 0), 2)

    def _draw_metrics(self, frame: np.ndarray, result: AnalysisResult) -> None:
        m = result.metrics
        lines = [
            f"phase: {result.phase}",
            f"rep: {result.rep_id}",
            f"knee: {fmt(m.get('knee_angle'))} deg",
            f"torso: {fmt(m.get('torso_angle'))} deg",
            f"depth: {fmt(m.get('depth_ratio'), 3)}",
            f"pose: {fmt(m.get('pose_score'), 2)}",
        ]
        y = 28
        for line in lines:
            cv2.putText(
                frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2
            )
            y += 26
        if result.fault_events:
            fault = result.fault_events[-1]
            text = f"FAULT: {fault.code} ({fault.severity})"
            cv2.putText(
                frame,
                text,
                (16, y + 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 0, 255),
                2,
            )


def fmt(v, ndigits: int = 1) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):.{ndigits}f}"
    except Exception:
        return str(v)
