from __future__ import annotations

from squat_ai_mvp.core.biomechanics.schemas import (
    AnalysisResult,
    FaultEvent,
    FrameEvent,
    Keypoint,
    PoseFrame,
    RepEvent,
)


def test_frame_event_defaults():
    ev = FrameEvent(
        session_id="s1",
        camera_id="c1",
        camera_role="side",
        frame_id=1,
        timestamp_ms=100,
        width=1280,
        height=720,
        fps_est=30.0,
    )
    assert ev.session_id == "s1"
    assert ev.camera_role == "side"
    assert ev.to_dict()["frame_id"] == 1


def test_keypoint():
    kp = Keypoint(name="left_knee", x=0.5, y=0.3, score=0.95)
    d = kp.to_dict()
    assert d["name"] == "left_knee"
    assert d["score"] == 0.95


def test_pose_frame():
    kp = Keypoint("nose", 100, 200, 0.9)
    ev = FrameEvent("s1", "c1", "side", 1, 0, 1280, 720, 30.0)
    pf = PoseFrame(
        frame=ev, keypoints={"nose": kp}, bbox=(50, 50, 500, 600), mean_score=0.9
    )
    d = pf.to_dict()
    assert d["mean_score"] == 0.9
    bbox = d["bbox"]
    assert (
        bbox is not None
        and bbox[0] == 50
        and bbox[1] == 50
        and bbox[2] == 500
        and bbox[3] == 600
    )
    assert d["keypoints"]["nose"]["x"] == 100


def test_pose_frame_no_bbox():
    kp = Keypoint("nose", 100, 200, 0.9)
    ev = FrameEvent("s1", "c1", "side", 1, 0, 1280, 720, 30.0)
    pf = PoseFrame(frame=ev, keypoints={"nose": kp})
    assert pf.bbox is None


def test_rep_event():
    rep = RepEvent(
        type="rep",
        exercise="squat",
        rep_id=1,
        start_ms=0,
        end_ms=1500,
        duration_ms=1500,
    )
    d = rep.to_dict()
    assert d["rep_id"] == 1
    assert d["duration_ms"] == 1500


def test_rep_event_with_metrics():
    rep = RepEvent(
        type="rep",
        exercise="squat",
        rep_id=2,
        start_ms=1000,
        end_ms=3000,
        duration_ms=2000,
        metrics={"min_knee_angle": 90.5, "max_depth_ratio": 0.05},
    )
    assert rep.metrics["min_knee_angle"] == 90.5


def test_fault_event():
    fault = FaultEvent(
        type="fault",
        exercise="squat",
        rep_id=1,
        phase="ascent",
        code="depth_not_enough",
        severity="medium",
        confidence=0.8,
        start_ms=2000,
        end_ms=2500,
        message="深蹲深度不够",
    )
    d = fault.to_dict()
    assert d["code"] == "depth_not_enough"
    assert d["confidence"] == 0.8


def test_fault_event_with_evidence():
    fault = FaultEvent(
        type="fault",
        exercise="squat",
        rep_id=1,
        phase="ascent",
        code="hip_rise_too_early",
        severity="high",
        confidence=0.85,
        start_ms=3000,
        end_ms=3500,
        message="hip rise",
        evidence={"torso_delta": 8.5, "knee_angle": 120.0},
    )
    assert fault.evidence["torso_delta"] == 8.5


def test_analysis_result():
    result = AnalysisResult(phase="descent", rep_id=0, metrics={"knee_angle": 130.0})
    d = result.to_dict()
    assert d["phase"] == "descent"
    assert d["rep_event"] is None
    assert d["fault_events"] == []


def test_analysis_result_with_rep_and_faults():
    fault = FaultEvent(
        "fault",
        "squat",
        1,
        "ascent",
        "torso_lean_too_much",
        "medium",
        0.7,
        100,
        200,
        "torso",
    )
    rep = RepEvent("rep", "squat", 1, 0, 1500, 1500)
    result = AnalysisResult(
        phase="ascent", rep_id=1, metrics={}, rep_event=rep, fault_events=[fault]
    )
    d = result.to_dict()
    assert d["rep_event"]["rep_id"] == 1
    assert len(d["fault_events"]) == 1
    assert d["fault_events"][0]["code"] == "torso_lean_too_much"
