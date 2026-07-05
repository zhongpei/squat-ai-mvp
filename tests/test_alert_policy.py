from __future__ import annotations

from squat_ai_mvp.core.alert.policy import AlertPolicy
from squat_ai_mvp.core.biomechanics.schemas import FaultEvent


def _fault(code: str, rep_id: int = 1, start_ms: int = 0, severity: str = "medium") -> FaultEvent:
    return FaultEvent(
        type="fault",
        exercise="squat",
        rep_id=rep_id,
        phase="ascent",
        code=code,
        severity=severity,
        confidence=0.8,
        start_ms=start_ms,
        end_ms=start_ms + 100,
        message=code,
    )


def test_disabled_returns_empty():
    policy = AlertPolicy(enabled=False)
    cmds = policy.filter_faults([_fault("depth_not_enough")])
    assert cmds == []


def test_passes_single_fault():
    policy = AlertPolicy(enabled=True)
    cmds = policy.filter_faults([_fault("depth_not_enough")])
    assert len(cmds) == 1
    assert cmds[0].cooldown_key == "squat.depth_not_enough"
    assert cmds[0].text == "depth_not_enough"


def test_cooldown_suppresses_duplicate():
    policy = AlertPolicy(enabled=True, same_fault_cooldown_ms=1000)
    cmds = policy.filter_faults([_fault("depth_not_enough", start_ms=0)])
    assert len(cmds) == 1
    cmds = policy.filter_faults([_fault("depth_not_enough", start_ms=500)])  # within cooldown
    assert len(cmds) == 0


def test_cooldown_expires():
    policy = AlertPolicy(enabled=True, same_fault_cooldown_ms=1000)
    policy.filter_faults([_fault("depth_not_enough", start_ms=0)])
    cmds = policy.filter_faults([_fault("depth_not_enough", start_ms=1500)])  # after cooldown
    assert len(cmds) == 1


def test_max_alerts_per_rep():
    policy = AlertPolicy(enabled=True, max_alerts_per_rep=2)
    # same rep, different fault types
    cmds = policy.filter_faults([
        _fault("depth_not_enough", rep_id=1, start_ms=100),
        _fault("torso_lean_too_much", rep_id=1, start_ms=200),
        _fault("hip_rise_too_early", rep_id=1, start_ms=300),
    ])
    assert len(cmds) == 2  # capped at 2 per rep


def test_max_alerts_per_set():
    policy = AlertPolicy(enabled=True, max_alerts_per_set=2)
    cmds = policy.filter_faults([
        _fault("depth_not_enough", rep_id=1, start_ms=100),
        _fault("torso_lean_too_much", rep_id=2, start_ms=200),
        _fault("hip_rise_too_early", rep_id=3, start_ms=300),
    ])
    assert len(cmds) == 2  # capped at 2 total


def test_low_severity_suppressed():
    policy = AlertPolicy(enabled=True)
    cmds = policy.filter_faults([_fault("pose_low_confidence", severity="low")])
    assert cmds == []


def test_mixed_severity():
    policy = AlertPolicy(enabled=True)
    cmds = policy.filter_faults([
        _fault("pose_low_confidence", severity="low"),
        _fault("depth_not_enough", severity="medium"),
        _fault("pose_low_confidence", severity="low"),
    ])
    assert len(cmds) == 1
    assert cmds[0].cooldown_key == "squat.depth_not_enough"


def test_different_faults_different_cooldowns():
    policy = AlertPolicy(enabled=True, same_fault_cooldown_ms=1000)
    cmds = policy.filter_faults([
        _fault("depth_not_enough", start_ms=0),
        _fault("torso_lean_too_much", start_ms=100),
    ])
    assert len(cmds) == 2  # different keys, both pass
