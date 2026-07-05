from __future__ import annotations

import math
from collections import deque
from typing import Optional

import numpy as np

from squat_ai_mvp.core.biomechanics.schemas import Keypoint


def valid(kp: Optional[Keypoint], min_score: float = 0.35) -> bool:
    return kp is not None and kp.score >= min_score and kp.x > 0 and kp.y > 0


def angle_deg(a: Keypoint, b: Keypoint, c: Keypoint) -> Optional[float]:
    if not (valid(a) and valid(b) and valid(c)):
        return None
    va = np.array([a.x - b.x, a.y - b.y], dtype=np.float64)
    vc = np.array([c.x - b.x, c.y - b.y], dtype=np.float64)
    na = np.linalg.norm(va)
    nc = np.linalg.norm(vc)
    if na == 0 or nc == 0:
        return None
    cos = float(np.dot(va, vc) / (na * nc))
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def midpoint(a: Keypoint, b: Keypoint, name: str = "mid") -> Optional[Keypoint]:
    if not (valid(a) and valid(b)):
        return None
    return Keypoint(name=name, x=(a.x + b.x) / 2, y=(a.y + b.y) / 2, score=min(a.score, b.score))


def torso_angle_from_vertical(shoulder_mid: Keypoint, hip_mid: Keypoint) -> Optional[float]:
    if not (valid(shoulder_mid) and valid(hip_mid)):
        return None
    dx = shoulder_mid.x - hip_mid.x
    dy = shoulder_mid.y - hip_mid.y
    if abs(dy) < 1e-6:
        return 90.0
    return abs(math.degrees(math.atan2(dx, dy)))


def body_height_proxy(shoulder_mid: Keypoint, ankle_mid: Keypoint) -> float:
    return max(1.0, abs(ankle_mid.y - shoulder_mid.y))


class MedianSmoother:
    def __init__(self, window: int = 5) -> None:
        self.values: dict[str, deque[float]] = {}
        self.window = max(1, int(window))

    def update(self, name: str, value: Optional[float]) -> Optional[float]:
        if value is None or math.isnan(value):
            return None
        q = self.values.setdefault(name, deque(maxlen=self.window))
        q.append(float(value))
        if len(q) == 1:
            return float(value)
        arr = np.array(q, dtype=np.float64)
        med = np.median(arr)
        std = np.std(arr)
        if std > 1e-6:
            arr = arr[np.abs(arr - med) <= 2.0 * std]
        return float(np.mean(arr)) if len(arr) else float(value)
