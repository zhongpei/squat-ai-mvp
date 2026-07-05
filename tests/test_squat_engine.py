from squat_ai_mvp.core.biomechanics.squat_engine import SquatSideEngine


def test_engine_constructs():
    rules = {
        "exercise": "squat",
        "phases": {"up_angle": 155, "bottom_angle": 112, "ascent_hysteresis": 8},
        "metrics": {"depth_min_ratio": -0.015, "torso_lean_max_deg": 45},
        "faults": {
            "depth_not_enough": {"severity": "medium", "message": "depth"},
            "torso_lean_too_much": {"severity": "medium", "message": "torso"},
            "hip_rise_too_early": {"severity": "high", "message": "hip"},
            "pose_low_confidence": {"severity": "low", "message": "pose"},
        },
    }
    engine = SquatSideEngine(rules)
    result = engine.analyze(None)
    assert result.phase == "setup"
    assert result.metrics["pose_ok"] is False
