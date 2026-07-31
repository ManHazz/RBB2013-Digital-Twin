# Save at: tests/integration/test_planner_to_dispatcher.py
#
# Integration: motion-planner's PlanResponse.joints must be a valid
# DispatchRequest for dispatcher. Dispatcher's ZMQ socket is mocked out
# so we test the HTTP contract in isolation.

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.dispatcher import app as disp_module
from services.motion_planner.app import app as mp_app


@pytest.fixture(autouse=True)
def _mock_zmq(monkeypatch):
    fake_socket = MagicMock()
    monkeypatch.setattr(disp_module, "socket", fake_socket)
    yield fake_socket


def test_planner_output_is_valid_dispatcher_input():
    with TestClient(mp_app) as mp:
        r = mp.post("/plan", json={"target": {"x": 40.0, "y": 13.75, "z": 0.0}})
        assert r.status_code == 200
        plan = r.json()
        assert plan["reachable"] is True
        joints = plan["joints"]
        assert len(joints) == 6

    with TestClient(disp_module.app) as disp:
        r2 = disp.post("/dispatch", json={"joints": joints})
        assert r2.status_code == 200, r2.text
        assert r2.json()["accepted"] is True


def test_unreachable_target_not_dispatched():
    with TestClient(mp_app) as mp:
        r = mp.post("/plan", json={"target": {"x": 999.0, "y": 999.0, "z": 999.0}})
        assert r.status_code == 200
        assert r.json()["reachable"] is False
