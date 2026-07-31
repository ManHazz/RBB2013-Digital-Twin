# Integration test: nl-command's output must be a valid PlanRequest.target
# for motion-planner. Ollama is stubbed; motion-planner runs its real IK.

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from services.motion_planner.app import app as mp_app
from services.nl_command import app as nl_module


FAKE_OLLAMA_RESPONSE = {
    "response": json.dumps([
        {"action": "above", "wait": 1.0},
        {"action": "grab", "wait": 1.0},
    ])
}


class _StubOllamaClient:
    """Replaces httpx.AsyncClient inside nl_command.app.ask_llm."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, timeout=None):
        request = httpx.Request("POST", url, json=json)
        return httpx.Response(200, json=FAKE_OLLAMA_RESPONSE, request=request)


@pytest.fixture(autouse=True)
def _patch_ollama(monkeypatch):
    monkeypatch.setattr(nl_module, "httpx", type("m", (), {
        "AsyncClient": _StubOllamaClient,
        "HTTPError": httpx.HTTPError,
    }))
    yield


def test_nl_output_is_valid_planner_input():
    """nl-command produces a TargetPose that motion-planner accepts as PlanRequest.target."""
    with TestClient(nl_module.app) as nl:
        r = nl.post("/command", json={"text": "pick up the ball"})
        assert r.status_code == 200, r.text
        target = r.json()

    assert set(target.keys()) >= {"x", "y", "z"}, f"nl-command response missing xyz: {target}"

    with TestClient(mp_app) as mp:
        r2 = mp.post("/plan", json={"target": {"x": target["x"], "y": target["y"], "z": target["z"]}})
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert "joints" in data and len(data["joints"]) == 6
        assert isinstance(data["reachable"], bool)
        assert isinstance(data["collision_free"], bool)