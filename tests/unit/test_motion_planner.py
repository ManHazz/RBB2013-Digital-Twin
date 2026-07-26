import math
from services.motion_planner import robot_ik as ik


def test_ik_roundtrip_reachable_target():
    target = (35.0, 5.0, 10.0)
    assert ik.reachable(*target)

    angles = ik.solve(*target)
    tip = ik.gripper_tip(angles)

    err = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, tip)))
    assert err < 1e-3


def test_unreachable_target_returns_false_not_error():
    x, y, z = 200.0, 200.0, 200.0
    assert not ik.reachable(x, y, z)