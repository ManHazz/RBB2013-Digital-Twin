import httpx
from fastapi.testclient import TestClient

from services.nl_command.app import app


def make_client(ollama_response_text: str) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": ollama_response_text})

    transport = httpx.MockTransport(handler)

    import services.nl_command.app as app_module
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

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