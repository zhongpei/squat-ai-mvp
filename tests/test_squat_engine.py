from __future__ import annotations

import math

from squat_ai_mvp.core.biomechanics.schemas import FrameEvent, Keypoint, PoseFrame
from squat_ai_mvp.core.biomechanics.squat_engine import SquatSideEngine

_RULES = {
    "exercise": "squat",
    "phases": {"up_angle": 155, "bottom_angle": 112, "ascent_hysteresis": 8},
    "metrics": {
        "depth_min_ratio": -0.015,
        "torso_lean_max_deg": 45,
        "hip_rise_torso_delta_deg": 7,
        "hip_rise_knee_angle_max": 135,
    },
    "faults": {
        "depth_not_enough": {"severity": "medium", "message": "depth"},
        "torso_lean_too_much": {"severity": "medium", "message": "torso"},
        "hip_rise_too_early": {"severity": "high", "message": "hip"},
        "pose_low_confidence": {"severity": "low", "message": "pose"},
    },
}


def _kp(name: str, x: float, y: float, score: float = 1.0) -> Keypoint:
    return Keypoint(name=name, x=x, y=y, score=score)


def _make_frame(
    frame_id: int, ts_ms: int, kps: dict[str, Keypoint], score: float = 0.9
) -> PoseFrame:
    ev = FrameEvent("s1", "c1", "side", frame_id, ts_ms, 1280, 720, 30.0)
    xs = [k.x for k in kps.values() if k.score >= 0.35]
    ys = [k.y for k in kps.values() if k.score >= 0.35]
    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None
    return PoseFrame(frame=ev, keypoints=kps, bbox=bbox, mean_score=score)


def _standing_pose(frame_id: int, ts_ms: int) -> PoseFrame:
    """Side-view standing pose, knee ~175deg, torso ~0deg lean."""
    kps = {
        "left_shoulder": _kp("left_shoulder", 480, 100),
        "right_shoulder": _kp("right_shoulder", 520, 100),
        "left_hip": _kp("left_hip", 480, 300),
        "right_hip": _kp("right_hip", 520, 300),
        "left_knee": _kp("left_knee", 475, 500),
        "right_knee": _kp("right_knee", 525, 500),
        "left_ankle": _kp("left_ankle", 470, 700),
        "right_ankle": _kp("right_ankle", 530, 700),
        "left_heel": _kp("left_heel", 470, 705),
        "right_heel": _kp("right_heel", 530, 705),
        "left_foot_index": _kp("left_foot_index", 465, 700),
        "right_foot_index": _kp("right_foot_index", 535, 700),
        "nose": _kp("nose", 500, 60),
    }
    return _make_frame(frame_id, ts_ms, kps)


def _bent_pose(
    frame_id: int, ts_ms: int, knee_deg: float = 100, torso_deg: float = 30
) -> PoseFrame:
    """Side-view bent knee position. Returns verified angles within ±0.5deg."""
    offset_angle = math.radians((180 - knee_deg) / 2)
    x_off = 200 * math.tan(offset_angle) if abs(math.cos(offset_angle)) > 1e-6 else 200

    tr = math.radians(torso_deg)
    shoulder_forward = 300 * math.sin(tr)
    shoulder_up = 300 * math.cos(tr)

    hip_x, hip_y = 500, 300
    kps = {
        "left_shoulder": _kp(
            "left_shoulder", hip_x - 20 + shoulder_forward, hip_y - shoulder_up
        ),
        "right_shoulder": _kp(
            "right_shoulder", hip_x + 20 + shoulder_forward, hip_y - shoulder_up
        ),
        "left_hip": _kp("left_hip", hip_x - 20, hip_y),
        "right_hip": _kp("right_hip", hip_x + 20, hip_y),
        "left_knee": _kp("left_knee", hip_x - 20 + x_off, hip_y + 200),
        "right_knee": _kp("right_knee", hip_x + 20 + x_off, hip_y + 200),
        "left_ankle": _kp("left_ankle", hip_x - 20, hip_y + 400),
        "right_ankle": _kp("right_ankle", hip_x + 20, hip_y + 400),
        "left_heel": _kp("left_heel", hip_x - 20, hip_y + 405),
        "right_heel": _kp("right_heel", hip_x + 20, hip_y + 405),
        "left_foot_index": _kp("left_foot_index", hip_x - 25, hip_y + 400),
        "right_foot_index": _kp("right_foot_index", hip_x + 25, hip_y + 400),
        "nose": _kp("nose", hip_x + shoulder_forward, hip_y - shoulder_up - 40),
    }
    return _make_frame(frame_id, ts_ms, kps)


def _low_conf_pose(pose: PoseFrame, score: float = 0.2) -> PoseFrame:
    """Return a copy of pose with keypoint scores and mean_score lowered."""
    for kp in pose.keypoints.values():
        kp.score = score
    pose.mean_score = score
    return pose


# ─── Tests ───


class TestEngineLifecycle:
    def test_constructs(self):
        engine = SquatSideEngine(_RULES, descent_confirm_ms=0)
        result = engine.analyze(None)
        assert result.phase == "setup"
        assert result.metrics["pose_ok"] == False

    def test_standing_stays_in_lockout(self):
        engine = SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)
        for _i in range(5):
            result = engine.analyze(_standing_pose(0, 0))
            assert result.phase == "setup" or result.phase == "lockout"


class TestPhaseTransitions:
    def _make_engine(self) -> SquatSideEngine:
        return SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)

    def test_descent_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        r = engine.analyze(_bent_pose(1, 33, knee_deg=145))
        assert r.phase == "descent"

    def test_bottom_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=145))
        r = engine.analyze(_bent_pose(2, 66, knee_deg=110))
        assert r.phase == "bottom"

    def test_ascent_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=145))
        engine.analyze(_bent_pose(2, 66, knee_deg=110))
        r = engine.analyze(_bent_pose(3, 100, knee_deg=125))
        assert r.phase == "ascent"

    def test_lockout_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=145))
        engine.analyze(_bent_pose(2, 66, knee_deg=110))
        engine.analyze(_bent_pose(3, 100, knee_deg=125))
        r = engine.analyze(_bent_pose(4, 133, knee_deg=160))
        assert r.phase == "lockout"

    def test_full_rep_cycle_counts_rep(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 100, knee_deg=145))  # descent starts here
        engine.analyze(_bent_pose(2, 400, knee_deg=105))  # bottom
        engine.analyze(_bent_pose(3, 600, knee_deg=125))  # ascent
        r = engine.analyze(_bent_pose(4, 900, knee_deg=160))  # lockout, dur=800 >= 700
        assert r.rep_event is not None, f"Result: phase={r.phase}, rep_id={r.rep_id}"
        assert r.rep_event.rep_id == 1
        assert r.rep_event.duration_ms >= 700

    def test_phase_transitions_correct_order(self):
        engine = self._make_engine()
        phases = []

        for i in range(3):
            r = engine.analyze(_standing_pose(i, i * 33))
            phases.append(r.phase)

        for i, deg in enumerate([148, 142, 136, 130, 110]):
            r = engine.analyze(_bent_pose(10 + i, 100 + i * 33, knee_deg=deg))
            phases.append(r.phase)

        for i, deg in enumerate([118, 125, 135, 145, 160]):
            r = engine.analyze(_bent_pose(20 + i, 300 + i * 33, knee_deg=deg))
            phases.append(r.phase)

        assert "descent" in phases, f"Phases: {phases}"
        assert "bottom" in phases, f"Phases: {phases}"
        assert "ascent" in phases, f"Phases: {phases}"
        assert "lockout" in phases, f"Phases: {phases}"


class TestDepthFault:
    def _make_engine(self) -> SquatSideEngine:
        return SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)

    def test_reversing_before_bottom_triggers_depth_fault(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=145))  # descent
        engine.analyze(_bent_pose(2, 66, knee_deg=140))  # deeper
        r = engine.analyze(
            _bent_pose(3, 99, knee_deg=150)
        )  # reversed (150 > 140+8=148)
        assert any(f.code == "depth_not_enough" for f in r.fault_events), (
            f"No depth fault in {[f.code for f in r.fault_events]}"
        )

    def test_deep_squat_no_depth_fault(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=145))
        engine.analyze(_bent_pose(2, 66, knee_deg=105))  # deep
        engine.analyze(_bent_pose(3, 99, knee_deg=125))
        r = engine.analyze(_bent_pose(4, 132, knee_deg=160))
        assert not any(f.code == "depth_not_enough" for f in r.fault_events)


class TestTorsoLeanFault:
    def _make_engine(self) -> SquatSideEngine:
        return SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)

    def test_excessive_lean_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        # Need 300ms continuous lean for torso fault
        for i in range(10):
            ts = 33 + i * 50
            engine.analyze(_bent_pose(1 + i, ts, knee_deg=140, torso_deg=50))
        r = engine.analyze(_bent_pose(11, 550, knee_deg=130, torso_deg=50))
        assert any(f.code == "torso_lean_too_much" for f in r.fault_events), (
            f"No torso fault in {[f.code for f in r.fault_events]}"
        )

    def test_normal_lean_no_fault(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        engine.analyze(_bent_pose(1, 33, knee_deg=140, torso_deg=20))
        engine.analyze(_bent_pose(2, 66, knee_deg=130, torso_deg=20))
        r = engine.analyze(_bent_pose(3, 99, knee_deg=120, torso_deg=20))
        assert not any(f.code == "torso_lean_too_much" for f in r.fault_events)


class TestHipRiseFault:
    def _make_engine(self) -> SquatSideEngine:
        return SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)

    def test_hip_rise_detected(self):
        engine = self._make_engine()
        engine.analyze(_standing_pose(0, 0))
        # Descent to bottom
        for i, deg in enumerate([148, 140, 130, 120, 110]):
            engine.analyze(_bent_pose(1 + i, 33 + i * 33, knee_deg=deg, torso_deg=30))

        # Ascent with excessive torso angle increase (hip rises before knee extends)
        r2 = engine.analyze(_bent_pose(10, 300, knee_deg=120, torso_deg=42))
        r2 = engine.analyze(_bent_pose(11, 333, knee_deg=128, torso_deg=48))
        has_fault = any(f.code == "hip_rise_too_early" for f in r2.fault_events)
        assert has_fault, f"No hip_rise fault in {[f.code for f in r2.fault_events]}"


class TestGoodSquat:
    def _make_engine(self) -> SquatSideEngine:
        return SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)

    def test_no_faults_on_good_squat(self):
        engine = self._make_engine()
        r = engine.analyze(_standing_pose(0, 0))
        # Descent deep with normal lean
        for i, deg in enumerate([150, 140, 130, 120, 110, 105]):
            r = engine.analyze(
                _bent_pose(1 + i, 33 + i * 33, knee_deg=deg, torso_deg=30)
            )
        assert r.phase == "bottom"
        # Ascend with synchronized movement
        for i, deg in enumerate([115, 125, 135, 145, 155, 160]):
            r = engine.analyze(
                _bent_pose(10 + i, 300 + i * 33, knee_deg=deg, torso_deg=30)
            )

        all_faults = sum(len(r.fault_events) for r in [r])
        assert all_faults == 0, "Expected no faults, got faults"


class TestLowConfidence:
    def test_low_conf_pose(self):
        engine = SquatSideEngine(_RULES, smoothing_window=1, descent_confirm_ms=0)
        pf = _standing_pose(0, 0)
        _low_conf_pose(pf, score=0.2)
        result = engine.analyze(pf)
        assert result.metrics["pose_score"] < 0.35
        assert result.metrics.get("knee_angle") is None  # no valid keypoints
