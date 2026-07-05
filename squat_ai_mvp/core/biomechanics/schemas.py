from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Optional


@dataclass
class FrameEvent:
    session_id: str
    camera_id: str
    camera_role: str
    frame_id: int
    timestamp_ms: int
    width: int
    height: int
    fps_est: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Keypoint:
    name: str
    x: float
    y: float
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PoseFrame:
    frame: FrameEvent
    keypoints: dict[str, Keypoint]
    bbox: Optional[tuple[float, float, float, float]] = None
    mean_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame.to_dict(),
            "keypoints": {name: kp.to_dict() for name, kp in self.keypoints.items()},
            "bbox": self.bbox,
            "mean_score": self.mean_score,
        }


@dataclass
class RepEvent:
    type: str
    exercise: str
    rep_id: int
    start_ms: int
    end_ms: int
    duration_ms: int
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FaultEvent:
    type: str
    exercise: str
    rep_id: int
    phase: str
    code: str
    severity: str
    confidence: float
    start_ms: int
    end_ms: int
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    phase: str
    rep_id: int
    metrics: dict[str, Any]
    rep_event: Optional[RepEvent] = None
    fault_events: list[FaultEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "rep_id": self.rep_id,
            "metrics": self.metrics,
            "rep_event": self.rep_event.to_dict() if self.rep_event else None,
            "fault_events": [e.to_dict() for e in self.fault_events],
        }
