from __future__ import annotations

from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

from squat_ai_mvp.core.biomechanics.schemas import Keypoint, PoseFrame
from squat_ai_mvp.core.stream.source import VideoFrame


MP_LANDMARK_NAMES = {
    0: "nose",
    11: "left_shoulder",
    12: "right_shoulder",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot_index",
    32: "right_foot_index",
}

# Used for overlay drawing.
POSE_CONNECTIONS = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("left_ankle", "left_heel"),
    ("left_heel", "left_foot_index"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("right_ankle", "right_heel"),
    ("right_heel", "right_foot_index"),
]


class MediaPipePoseEstimator:
    """MediaPipe Pose adapter.

    The rest of the system uses our own PoseFrame schema, so this adapter can later be
    replaced by RTMPose/RTMW/MMPose without changing the biomechanics engine.
    """

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.55,
        min_keypoint_score: float = 0.45,
    ) -> None:
        self.min_keypoint_score = min_keypoint_score
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            smooth_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def close(self) -> None:
        self._pose.close()

    def infer(self, video_frame: VideoFrame) -> Optional[PoseFrame]:
        image = video_frame.image_bgr
        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return None

        keypoints: dict[str, Keypoint] = {}
        scores: list[float] = []
        xs: list[float] = []
        ys: list[float] = []
        for idx, name in MP_LANDMARK_NAMES.items():
            lm = result.pose_landmarks.landmark[idx]
            score = float(lm.visibility)
            x = float(lm.x * w)
            y = float(lm.y * h)
            keypoints[name] = Keypoint(name=name, x=x, y=y, score=score)
            if score >= self.min_keypoint_score:
                scores.append(score)
                xs.append(x)
                ys.append(y)

        bbox = None
        if xs and ys:
            bbox = (min(xs), min(ys), max(xs), max(ys))
        mean_score = float(np.mean(scores)) if scores else 0.0
        return PoseFrame(frame=video_frame.event, keypoints=keypoints, bbox=bbox, mean_score=mean_score)
