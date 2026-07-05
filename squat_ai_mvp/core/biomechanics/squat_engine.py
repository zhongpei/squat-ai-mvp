from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from squat_ai_mvp.core.biomechanics.math_utils import (
    MedianSmoother,
    angle_deg,
    body_height_proxy,
    midpoint,
)
from squat_ai_mvp.core.biomechanics.math_utils import torso_angle_from_vertical
from squat_ai_mvp.core.biomechanics.schemas import (
    AnalysisResult,
    FaultEvent,
    PoseFrame,
    RepEvent,
)


@dataclass
class RepState:
    start_ms: int = 0
    bottom_ms: int = 0
    min_knee_angle: float = 999.0
    max_torso_angle: float = 0.0
    max_depth_ratio: float = -999.0
    bottom_torso_angle: Optional[float] = None
    hip_y_at_bottom: Optional[float] = None
    hip_rise_fault_emitted: bool = False
    torso_fault_active_since: Optional[int] = None
    low_conf_fault_active_since: Optional[int] = None
    emitted_faults: set[str] = field(default_factory=set)


class SquatSideEngine:
    """Side-view squat phase/state and rules engine.

    This is intentionally independent from the pose backend. It receives PoseFrame
    and returns RepEvent/FaultEvent objects.
    """

    def __init__(
        self,
        rules: dict[str, Any],
        smoothing_window: int = 5,
        min_rep_duration_ms: int = 700,
        descent_confirm_ms: int = 300,
    ) -> None:
        self.rules = rules
        self.exercise = str(rules.get("exercise", "squat"))
        phase_cfg = rules.get("phases", {})
        metric_cfg = rules.get("metrics", {})
        self.up_angle = float(phase_cfg.get("up_angle", 155))
        self.bottom_angle = float(phase_cfg.get("bottom_angle", 112))
        self.ascent_hysteresis = float(phase_cfg.get("ascent_hysteresis", 8))
        self.depth_min_ratio = float(metric_cfg.get("depth_min_ratio", -0.015))
        self.torso_lean_max_deg = float(metric_cfg.get("torso_lean_max_deg", 45))
        self.hip_rise_torso_delta_deg = float(
            metric_cfg.get("hip_rise_torso_delta_deg", 7)
        )
        self.hip_rise_knee_angle_max = float(
            metric_cfg.get("hip_rise_knee_angle_max", 135)
        )
        self.min_rep_duration_ms = int(min_rep_duration_ms)
        self.smoother = MedianSmoother(smoothing_window)
        self.phase = "setup"
        self.rep_id = 0
        self.rep = RepState()
        self.last_knee_angle: Optional[float] = None
        self.last_phase_change_ms = 0
        # Sustained descent guard: knee must stay below threshold for N ms
        # to prevent noise-triggered false descent.
        self._descent_candidate_ms: Optional[int] = None
        self._descent_confirm_ms = descent_confirm_ms

    def analyze(self, pose: Optional[PoseFrame]) -> AnalysisResult:
        if pose is None:
            return AnalysisResult(
                phase=self.phase, rep_id=self.rep_id, metrics={"pose_ok": False}
            )

        metrics = self._extract_metrics(pose)
        now_ms = pose.frame.timestamp_ms
        faults: list[FaultEvent] = []

        if metrics["pose_score"] < 0.35:
            low = self._duration_fault(
                code="pose_low_confidence",
                phase=self.phase,
                severity="low",
                message=self._fault_message("pose_low_confidence"),
                since_attr="low_conf_fault_active_since",
                now_ms=now_ms,
                min_ms=600,
                evidence={"pose_score": metrics["pose_score"]},
            )
            if low:
                faults.append(low)

        knee_angle = metrics.get("knee_angle")
        if knee_angle is None:
            return AnalysisResult(
                phase=self.phase,
                rep_id=self.rep_id,
                metrics=metrics,
                fault_events=faults,
            )

        previous_phase = self.phase
        rep_event: Optional[RepEvent] = None

        # Start or continue rep metrics.
        if self.phase in ("descent", "bottom", "ascent"):
            self._update_rep_metrics(metrics, now_ms)

        if self.phase in ("setup", "lockout"):
            if knee_angle < self.up_angle - 8:
                # Sustained descent guard: knee must stay below threshold for N ms.
                # With confirm=0, transition immediately on first frame.
                if self._descent_candidate_ms is None:
                    self._descent_candidate_ms = now_ms
                    if self._descent_confirm_ms <= 0:
                        self.phase = "descent"
                        self.rep = RepState(start_ms=now_ms)
                        self._update_rep_metrics(metrics, now_ms)
                elif now_ms - self._descent_candidate_ms >= self._descent_confirm_ms:
                    self.phase = "descent"
                    self.rep = RepState(start_ms=now_ms)
                    self._update_rep_metrics(metrics, now_ms)
            else:
                self._descent_candidate_ms = None
                self.phase = "lockout"

        elif self.phase == "descent":
            if knee_angle <= self.bottom_angle:
                self.phase = "bottom"
                self.rep.bottom_ms = now_ms
                self.rep.bottom_torso_angle = metrics.get("torso_angle")
                self.rep.hip_y_at_bottom = metrics.get("hip_y")
            elif (
                self.last_knee_angle is not None
                and knee_angle > self.last_knee_angle + self.ascent_hysteresis
            ):
                # User reversed before reaching bottom angle. Treat as shallow bottom.
                self.phase = "ascent"
                self.rep.bottom_ms = now_ms
                self.rep.bottom_torso_angle = metrics.get("torso_angle")
                self.rep.hip_y_at_bottom = metrics.get("hip_y")
                fault = self._rep_fault(
                    code="depth_not_enough",
                    phase="ascent",
                    severity=self._fault_severity("depth_not_enough"),
                    message=self._fault_message("depth_not_enough"),
                    now_ms=now_ms,
                    confidence=0.75,
                    evidence={
                        "gap_deg": round(
                            max(0, self.rep.min_knee_angle - self.bottom_angle), 1
                        ),
                        "knee_angle": round(self.rep.min_knee_angle, 1),
                        "target": self.bottom_angle,
                    },
                )
                faults.append(fault)

        elif self.phase == "bottom":
            if knee_angle > self.bottom_angle + self.ascent_hysteresis:
                self.phase = "ascent"
                if self.rep.max_depth_ratio < self.depth_min_ratio:
                    faults.append(
                        self._rep_fault(
                            code="depth_not_enough",
                            phase="ascent",
                            severity=self._fault_severity("depth_not_enough"),
                            message=self._fault_message("depth_not_enough"),
                            now_ms=now_ms,
                            confidence=0.8,
                            evidence={
                                "gap_deg": round(
                                    max(0, self.rep.min_knee_angle - self.bottom_angle),
                                    1,
                                ),
                                "knee_angle": round(self.rep.min_knee_angle, 1),
                                "target": self.bottom_angle,
                            },
                        )
                    )

        elif self.phase == "ascent":
            hip_rise_fault = self._check_hip_rise(metrics, now_ms)
            if hip_rise_fault:
                faults.append(hip_rise_fault)

            if knee_angle >= self.up_angle:
                duration = now_ms - self.rep.start_ms
                if duration >= self.min_rep_duration_ms:
                    self.rep_id += 1
                    rep_event = RepEvent(
                        type="rep",
                        exercise=self.exercise,
                        rep_id=self.rep_id,
                        start_ms=self.rep.start_ms,
                        end_ms=now_ms,
                        duration_ms=duration,
                        metrics={
                            "min_knee_angle": round(self.rep.min_knee_angle, 2),
                            "max_torso_angle": round(self.rep.max_torso_angle, 2),
                            "max_depth_ratio": round(self.rep.max_depth_ratio, 4),
                        },
                    )
                self.phase = "lockout"
                self.rep = RepState()

        # Continuous torso lean fault.
        torso_fault = self._check_torso_lean(metrics, now_ms)
        if torso_fault:
            faults.append(torso_fault)

        if previous_phase != self.phase:
            self.last_phase_change_ms = now_ms
        self.last_knee_angle = knee_angle

        metrics["phase"] = self.phase
        metrics["rep_id"] = self.rep_id
        return AnalysisResult(
            phase=self.phase,
            rep_id=self.rep_id,
            metrics=metrics,
            rep_event=rep_event,
            fault_events=faults,
        )

    def _extract_metrics(self, pose: PoseFrame) -> dict[str, Any]:
        k = pose.keypoints
        ls, rs = k.get("left_shoulder"), k.get("right_shoulder")
        lh, rh = k.get("left_hip"), k.get("right_hip")
        lk, rk = k.get("left_knee"), k.get("right_knee")
        la, ra = k.get("left_ankle"), k.get("right_ankle")

        left_knee = angle_deg(lh, lk, la) if lh and lk and la else None
        right_knee = angle_deg(rh, rk, ra) if rh and rk and ra else None
        knee_values = [v for v in (left_knee, right_knee) if v is not None]
        knee_angle = sum(knee_values) / len(knee_values) if knee_values else None
        knee_angle = self.smoother.update("knee_angle", knee_angle)

        shoulder_mid = midpoint(ls, rs, "shoulder_mid") if ls and rs else None
        hip_mid = midpoint(lh, rh, "hip_mid") if lh and rh else None
        knee_mid = midpoint(lk, rk, "knee_mid") if lk and rk else None
        ankle_mid = midpoint(la, ra, "ankle_mid") if la and ra else None

        torso_angle = None
        if shoulder_mid and hip_mid:
            torso_angle = torso_angle_from_vertical(shoulder_mid, hip_mid)
            torso_angle = self.smoother.update("torso_angle", torso_angle)

        depth_ratio = None
        if hip_mid and knee_mid and shoulder_mid and ankle_mid:
            height = body_height_proxy(shoulder_mid, ankle_mid)
            # y grows downward; larger means hip below knee.
            depth_ratio = (hip_mid.y - knee_mid.y) / height
            depth_ratio = self.smoother.update("depth_ratio", depth_ratio)

        hip_y = self.smoother.update("hip_y", hip_mid.y if hip_mid else None)

        return {
            "pose_ok": True,
            "pose_score": pose.mean_score,
            "knee_angle": knee_angle,
            "left_knee_angle": left_knee,
            "right_knee_angle": right_knee,
            "torso_angle": torso_angle,
            "depth_ratio": depth_ratio,
            "hip_y": hip_y,
            "timestamp_ms": pose.frame.timestamp_ms,
        }

    def _update_rep_metrics(self, metrics: dict[str, Any], now_ms: int) -> None:
        knee = metrics.get("knee_angle")
        torso = metrics.get("torso_angle")
        depth = metrics.get("depth_ratio")
        if knee is not None:
            self.rep.min_knee_angle = min(self.rep.min_knee_angle, float(knee))
        if torso is not None:
            self.rep.max_torso_angle = max(self.rep.max_torso_angle, float(torso))
        if depth is not None:
            self.rep.max_depth_ratio = max(self.rep.max_depth_ratio, float(depth))

    def _check_torso_lean(
        self, metrics: dict[str, Any], now_ms: int
    ) -> Optional[FaultEvent]:
        torso = metrics.get("torso_angle")
        if torso is None or self.phase not in ("descent", "bottom", "ascent"):
            self.rep.torso_fault_active_since = None
            return None
        if torso <= self.torso_lean_max_deg:
            self.rep.torso_fault_active_since = None
            return None
        if self.rep.torso_fault_active_since is None:
            self.rep.torso_fault_active_since = now_ms
            return None
        if now_ms - self.rep.torso_fault_active_since < 300:
            return None
        return self._rep_fault(
            code="torso_lean_too_much",
            phase=self.phase,
            severity=self._fault_severity("torso_lean_too_much"),
            message=self._fault_message("torso_lean_too_much"),
            now_ms=now_ms,
            confidence=min(0.95, 0.55 + (torso - self.torso_lean_max_deg) / 30),
            evidence={
                "excess_deg": round(float(torso) - self.torso_lean_max_deg, 1),
                "torso_angle": round(float(torso), 2),
                "threshold": self.torso_lean_max_deg,
            },
        )

    def _check_hip_rise(
        self, metrics: dict[str, Any], now_ms: int
    ) -> Optional[FaultEvent]:
        if self.rep.hip_rise_fault_emitted or self.phase != "ascent":
            return None
        torso = metrics.get("torso_angle")
        knee = metrics.get("knee_angle")
        if torso is None or knee is None or self.rep.bottom_torso_angle is None:
            return None
        torso_delta = float(torso) - float(self.rep.bottom_torso_angle)
        if (
            knee <= self.hip_rise_knee_angle_max
            and torso_delta >= self.hip_rise_torso_delta_deg
        ):
            self.rep.hip_rise_fault_emitted = True
            return self._rep_fault(
                code="hip_rise_too_early",
                phase="ascent",
                severity=self._fault_severity("hip_rise_too_early"),
                message=self._fault_message("hip_rise_too_early"),
                now_ms=now_ms,
                confidence=min(0.95, 0.65 + torso_delta / 30),
                evidence={
                    "torso_delta": round(torso_delta, 2),
                    "knee_angle": round(float(knee), 2),
                    "bottom_torso_angle": round(float(self.rep.bottom_torso_angle), 2),
                },
            )
        return None

    def _duration_fault(
        self,
        code: str,
        phase: str,
        severity: str,
        message: str,
        since_attr: str,
        now_ms: int,
        min_ms: int,
        evidence: dict[str, Any],
    ) -> Optional[FaultEvent]:
        since = getattr(self.rep, since_attr)
        if since is None:
            setattr(self.rep, since_attr, now_ms)
            return None
        if now_ms - since < min_ms:
            return None
        return self._rep_fault(code, phase, severity, message, now_ms, 0.6, evidence)

    def _rep_fault(
        self,
        code: str,
        phase: str,
        severity: str,
        message: str,
        now_ms: int,
        confidence: float,
        evidence: dict[str, Any],
    ) -> FaultEvent:
        return FaultEvent(
            type="fault",
            exercise=self.exercise,
            rep_id=self.rep_id + 1 if self.phase != "lockout" else self.rep_id,
            phase=phase,
            code=code,
            severity=severity,
            confidence=float(confidence),
            start_ms=now_ms,
            end_ms=now_ms,
            message=self._format_fault_message(code, evidence),
            evidence=evidence,
        )

    def _format_fault_message(self, code: str, evidence: dict[str, Any]) -> str:
        """Fill {placeholders} in the rule message with evidence values."""
        template = self._fault_message(code)
        try:
            return template.format(**evidence)
        except (KeyError, ValueError, TypeError):
            return template

    def _fault_message(self, code: str) -> str:
        return str(self.rules.get("faults", {}).get(code, {}).get("message", code))

    def _fault_severity(self, code: str) -> str:
        return str(self.rules.get("faults", {}).get(code, {}).get("severity", "medium"))
