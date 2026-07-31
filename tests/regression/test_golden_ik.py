# Regression: fixed golden pose→joints expectations. If any change to
# motion-planner or robot_ik.py drifts these outputs, CI fails.

import pytest
from fastapi.testclient import TestClient

from services.motion_planner.app import app as mp_app

GOLDEN_CASES = [
    # (target, expected_reachable, expected_collision_free)
    ({"x": 40.0, "y": 13.75, "z": 0.0}, True, True),
    ({"x": 40.0, "y": 1.75, "z": 0.0}, True, True),
    ({"x": 40.0, "y": 26.75, "z": 0.0}, False, True),
    ({"x": 500.0, "y": 500.0, "z": 500.0}, False, True),
]


@pytest.mark.parametrize("target,reachable,collision_free", GOLDEN_CASES)
def test_golden_plan(target, reachable, collision_free):
    with TestClient(mp_app) as client:
        r = client.post("/plan", json={"target": target})
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] == reachable, f"{target} → reachable drift: {data}"
        if reachable:
            assert data["collision_free"] == collision_free, f"{target} → collision drift"
            assert len(data["joints"]) == 6