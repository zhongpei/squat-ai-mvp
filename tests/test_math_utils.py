from __future__ import annotations


from squat_ai_mvp.core.biomechanics.math_utils import (
    MedianSmoother,
    angle_deg,
    body_height_proxy,
    midpoint,
    torso_angle_from_vertical,
    valid,
)
from squat_ai_mvp.core.biomechanics.schemas import Keypoint


def _kp(name: str, x: float, y: float, score: float = 1.0) -> Keypoint:
    return Keypoint(name=name, x=x, y=y, score=score)


class TestValid:
    def test_valid_keypoint(self):
        assert valid(_kp("a", 100, 200, 0.9))

    def test_low_score(self):
        assert not valid(_kp("a", 100, 200, 0.2))

    def test_zero_coords(self):
        assert not valid(_kp("a", 0, 0, 0.9))

    def test_none(self):
        assert not valid(None)


class TestAngleDeg:
    def test_right_angle(self):
        a = _kp("a", 10, 10)
        b = _kp("b", 10, 110)
        c = _kp("c", 110, 110)
        ang = angle_deg(a, b, c)
        assert ang is not None
        assert abs(ang - 90.0) < 0.01

    def test_straight_line(self):
        a = _kp("a", 10, 10)
        b = _kp("b", 10, 110)
        c = _kp("c", 10, 210)
        ang = angle_deg(a, b, c)
        assert ang is not None
        assert abs(ang - 180.0) < 0.01

    def test_acute(self):
        a = _kp("a", 10, 10)
        b = _kp("b", 10, 110)
        c = _kp("c", 110, 10)
        ang = angle_deg(a, b, c)
        assert ang is not None
        assert abs(ang - 45.0) < 0.01

    def test_invalid_keypoint_none(self):
        assert angle_deg(None, _kp("b", 10, 10), _kp("c", 10, 110)) is None  # type: ignore[arg-type]

    def test_invalid_keypoint_low_score(self):
        a = _kp("a", 10, 10, 0.2)
        b = _kp("b", 10, 110)
        c = _kp("c", 110, 110)
        assert angle_deg(a, b, c) is None

    def test_zero_vector(self):
        a = _kp("a", 10, 10)
        b = _kp("b", 10, 10)
        c = _kp("c", 110, 110)
        assert angle_deg(a, b, c) is None


class TestMidpoint:
    def test_basic_midpoint(self):
        a = _kp("a", 10, 10)
        b = _kp("b", 110, 210)
        m = midpoint(a, b, "mid")
        assert m is not None
        assert m.name == "mid"
        assert m.x == 60.0
        assert m.y == 110.0

    def test_invalid_input(self):
        assert midpoint(None, _kp("b", 100, 200)) is None  # type: ignore[arg-type]
        assert midpoint(_kp("a", 10, 10, 0.1), _kp("b", 100, 200)) is None

    def test_score_is_min(self):
        a = _kp("a", 10, 10, 0.8)
        b = _kp("b", 110, 210, 0.5)
        m = midpoint(a, b)
        assert m is not None
        assert m.score == 0.5


class TestTorsoAngle:
    def test_vertical_torso(self):
        shoulder = _kp("s", 100, 100)
        hip = _kp("h", 100, 300)
        angle = torso_angle_from_vertical(shoulder, hip)
        assert angle is not None
        assert angle < 1.0  # nearly 0

    def test_lean_forward(self):
        shoulder = _kp("s", 200, 100)
        hip = _kp("h", 100, 300)
        angle = torso_angle_from_vertical(shoulder, hip)
        assert angle is not None
        assert 10 < angle < 60  # some lean

    def test_invalid(self):
        assert torso_angle_from_vertical(_kp("s", 100, 200, 0.1), _kp("h", 100, 300)) is None

    def test_flat_line(self):
        shoulder = _kp("s", 10, 100)
        hip = _kp("h", 110, 100)
        angle = torso_angle_from_vertical(shoulder, hip)
        assert angle is not None
        assert abs(angle - 90.0) < 1.0


class TestBodyHeightProxy:
    def test_basic(self):
        shoulder = _kp("s", 100, 100)
        ankle = _kp("a", 100, 700)
        h = body_height_proxy(shoulder, ankle)
        assert h == 600.0

    def test_min_height(self):
        shoulder = _kp("s", 100, 700)
        ankle = _kp("a", 100, 700)
        h = body_height_proxy(shoulder, ankle)
        assert h >= 1.0


class TestMedianSmoother:
    def test_single_value(self):
        s = MedianSmoother(5)
        assert s.update("knee", 100.0) == 100.0

    def test_multiple_values(self):
        s = MedianSmoother(3)
        s.update("knee", 100.0)
        s.update("knee", 102.0)
        v = s.update("knee", 101.0)
        assert v is not None
        assert 100 <= v <= 102

    def test_outlier_rejection(self):
        s = MedianSmoother(5)
        vals = [100.0, 101.0, 99.0, 100.5, 200.0]  # 200 is outlier
        for v in vals:
            s.update("knee", v)
        last = s.update("knee", 100.0)
        assert last is not None
        assert last < 150.0  # outlier rejected

    def test_none_value(self):
        s = MedianSmoother(5)
        assert s.update("knee", None) is None
        s.update("knee", 100.0)
        assert s.update("knee", None) is None

    def test_nan_value(self):
        s = MedianSmoother(5)
        assert s.update("knee", float("nan")) is None

    def test_independent_streams(self):
        s = MedianSmoother(3)
        s.update("knee", 100.0)
        s.update("torso", 20.0)
        s.update("knee", 102.0)
        s.update("torso", 22.0)
        knee = s.update("knee", 101.0)
        torso = s.update("torso", 21.0)
        assert knee is not None
        assert torso is not None
