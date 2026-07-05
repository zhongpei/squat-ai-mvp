from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from squat_ai_mvp.core.biomechanics.schemas import Keypoint, PoseFrame
from squat_ai_mvp.core.stream.source import VideoFrame

# Lazy imports for mediapipe (heavy) so config/schemas load fast.
_MediaPipe: type | None = None
_PoseLandmarker: type | None = None
_PoseLandmarkerOptions: type | None = None
_PoseLandmark: type | None = None
_RunningMode: type | None = None
_BaseOptions: type | None = None
_Image: type | None = None
_ImageFormat: type | None = None


def _lazy_import_mediapipe():
    global _MediaPipe, _PoseLandmarker, _PoseLandmarkerOptions, _PoseLandmark
    global _RunningMode, _BaseOptions, _Image, _ImageFormat
    if _PoseLandmarker is not None:
        return
    import mediapipe as mp

    _MediaPipe = mp
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,  # noqa: N812
        PoseLandmarkerOptions,  # noqa: N812
        PoseLandmark,  # noqa: N812
        RunningMode,  # noqa: N812
    )
    from mediapipe.tasks.python import BaseOptions  # noqa: N812
    from mediapipe import Image as MpImage  # noqa: N812
    from mediapipe import ImageFormat  # noqa: N812

    _PoseLandmarker = PoseLandmarker
    _PoseLandmarkerOptions = PoseLandmarkerOptions
    _PoseLandmark = PoseLandmark
    _RunningMode = RunningMode
    _BaseOptions = BaseOptions
    _Image = MpImage
    _ImageFormat = ImageFormat


_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"
_MODEL_PATHS = {
    0: _MODEL_DIR / "pose_landmarker_lite.task",
    1: _MODEL_DIR / "pose_landmarker_full.task",
    2: _MODEL_DIR / "pose_landmarker_heavy.task",
}
_MODEL_URLS = {
    0: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    1: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    2: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}

# Named landmarks relevant for squat analysis.
# Maps our internal names to PoseLandmark enum members.
LANDMARK_MAP: dict[str, str] = {
    "nose": "NOSE",
    "left_shoulder": "LEFT_SHOULDER",
    "right_shoulder": "RIGHT_SHOULDER",
    "left_hip": "LEFT_HIP",
    "right_hip": "RIGHT_HIP",
    "left_knee": "LEFT_KNEE",
    "right_knee": "RIGHT_KNEE",
    "left_ankle": "LEFT_ANKLE",
    "right_ankle": "RIGHT_ANKLE",
    "left_heel": "LEFT_HEEL",
    "right_heel": "RIGHT_HEEL",
    "left_foot_index": "LEFT_FOOT_INDEX",
    "right_foot_index": "RIGHT_FOOT_INDEX",
}

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


def _ensure_model(complexity: int = 1) -> Path:
    """Return path to the pose landmarker model, downloading if missing.

    complexity: 0=Lite, 1=Full (default), 2=Heavy
    """
    complexity = max(0, min(2, int(complexity)))
    model_path = _MODEL_PATHS[complexity]  # 0:Lite, 1:Full, 2:Heavy
    if model_path.exists():
        return model_path
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = _MODEL_URLS[complexity]
    print(f"[perception] Downloading pose model ({url})...")
    import urllib.request

    urllib.request.urlretrieve(str(url), str(model_path))
    print(f"[perception] Model saved to {model_path}")
    return model_path


class MediaPipePoseEstimator:
    """MediaPipe Pose adapter using the Tasks API (PoseLandmarker).

    The rest of the system uses our own PoseFrame schema, so this adapter can later be
    replaced by RTMPose/RTMW/MMPose without changing the biomechanics engine.
    """

    def __init__(
        self,
        model_complexity: int = 1,
        delegate: str = "cpu",
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.55,
        min_keypoint_score: float = 0.45,
    ) -> None:
        self.min_keypoint_score = min_keypoint_score
        _lazy_import_mediapipe()

        model_path = _ensure_model(model_complexity)
        if delegate == "gpu":
            print(
                "[perception] WARNING: GPU delegate may crash on macOS Python (Metal format bug)."
            )
            print("[perception] Set delegate=cpu in config if crashes occur.")
        delegate_enum = (
            _BaseOptions.Delegate.GPU
            if delegate == "gpu"
            else _BaseOptions.Delegate.CPU
        )
        options = _PoseLandmarkerOptions(
            base_options=_BaseOptions(
                model_asset_path=str(model_path), delegate=delegate_enum
            ),
            running_mode=_RunningMode.IMAGE,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        try:
            self._landmarker = _PoseLandmarker.create_from_options(options)
        except Exception as exc:
            # GPU delegate may fail (e.g. Metal unavailable). Fall back to CPU.
            print(f"[perception] GPU delegate failed ({exc}); falling back to CPU")
            options.base_options.delegate = _BaseOptions.Delegate.CPU
            self._landmarker = _PoseLandmarker.create_from_options(options)

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def infer(self, video_frame: VideoFrame) -> Optional[PoseFrame]:
        image = video_frame.image_bgr
        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = _Image(image_format=_ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None

        landmarks = result.pose_landmarks[0]
        keypoints: dict[str, Keypoint] = {}
        scores: list[float] = []
        xs: list[float] = []
        ys: list[float] = []

        for name, enum_name in LANDMARK_MAP.items():
            idx = getattr(_PoseLandmark, enum_name)
            lm = landmarks[idx]
            score = float(lm.visibility)
            # Coordinates are normalized [0..1]; convert to pixels.
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
        return PoseFrame(
            frame=video_frame.event,
            keypoints=keypoints,
            bbox=bbox,
            mean_score=mean_score,
        )
