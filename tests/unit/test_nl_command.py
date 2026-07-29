import httpx
from fastapi.testclient import TestClient

from services.nl_command.app import app

# Capture the REAL AsyncClient exactly once. If we re-read httpx.AsyncClient
# inside make_client() on every call, each test would accidentally wrap the
# PREVIOUS test's mock instead of the true original, silently falling back
# to an earlier test's fake Ollama response.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def make_client(ollama_response_text: str) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": ollama_response_text})

    transport = httpx.MockTransport(handler)

    import services.nl_command.app as app_module

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    app_module.httpx.AsyncClient = patched_client
    return TestClient(app)


def test_happy_path():
    # Ollama returns a plan whose first real step is "above" the target.
    client = make_client(
        '[{"action":"home","wait":0.8},{"action":"above","wait":1.0}]'
    )
    resp = client.post("/command", json={"text": "pick up the ball"})
    assert resp.status_code == 200
    # FALLBACK_TARGET is x=40.0, y=1.75, z=0.0; "above" adds 12.0 to y.
    assert resp.json() == {"x": 40.0, "y": 13.75, "z": 0.0}


def test_empty_text_returns_422():
    client = make_client('[{"action":"home","wait":0.8}]')
    resp = client.post("/command", json={"text": ""})
    assert resp.status_code == 422


def test_garbled_ollama_returns_422():
    client = make_client("gibberish nonsense, not json at all")
    resp = client.post("/command", json={"text": "go here"})
    assert resp.status_code == 422


def test_home_only_plan_returns_422():
    client = make_client('[{"action":"home","wait":0.8}]')
    resp = client.post("/command", json={"text": "never mind"})
    assert resp.status_code == 422