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


OBSTACLES = [
    {"name": "obstacle_A", "x": 25.0, "y": 12.0, "z": 8.0, "r": 4.0},
    {"name": "obstacle_B", "x": 30.0, "y": 20.0, "z": -10.0, "r": 5.0},
]


def test_colliding_target_rejected():
    target = (25.0, 12.0, 8.0)
    assert ik.reachable(*target)
    angles = ik.solve(*target)
    assert ik.collides(angles, OBSTACLES)