# Sprint-1 Fixes — Ariq + Ibrohim

Reviewed by Aiman before the sprint-1 group merge. Two teammates have blockers that must be fixed before `feat/integration → main` can go up.

**How to use this file:** find your section. Do the tasks in order. One task = one commit. Push. When all your fixes are pushed, tell Aiman.

**Rule:** if you are unsure, message Aiman. Do NOT edit `services/shared/schemas.py` — that is the frozen contract.

---

## Ariq — 2 fixes (≈10 minutes)

Your code logic is fine. The Dockerfile just doesn't include the shared schemas, so the container will crash on the first request. And your files have a hidden UTF-8 BOM that breaks `docker build` on some systems.

### ☐ Ariq-FIX-01 — Rewrite motion-planner Dockerfile

**Branch:** `feat/motion-planner`

**Problem:** Your current Dockerfile is:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8020"]
```
Two issues: `COPY . .` doesn't include `services/shared/` (build context is wrong), and `app:app` won't resolve because `app.py` uses `from services.shared.schemas import ...`. Container starts, first `/plan` request → `ImportError`.

**Do exactly this:** replace `services/motion_planner/Dockerfile` with:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/motion_planner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/motion_planner /app/services/motion_planner

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.motion_planner.app:app", "--host", "0.0.0.0", "--port", "8020"]
```

**Done when:** `docker build -f services/motion_planner/Dockerfile -t motion-planner .` succeeds when run from repo root.

**Push:**
```bash
git add services/motion_planner/Dockerfile
git commit -m "Ariq-FIX-01: rewrite Dockerfile to include shared schemas"
git push
```

---

### ☐ Ariq-FIX-02 — Strip UTF-8 BOM from source files

**Branch:** `feat/motion-planner`

**Problem:** `app.py`, `Dockerfile`, and `requirements.txt` all start with a zero-width BOM byte (`﻿`). Python 3 tolerates it, but `docker build` on some Linux distros rejects a BOM in the Dockerfile with a cryptic parse error.

**Do exactly this:** in your editor, open each file, save as **UTF-8 without BOM** (VS Code: bottom-right encoding indicator → "Save with Encoding" → "UTF-8"). Or run this in the repo root:
```bash
for f in services/motion_planner/app.py services/motion_planner/Dockerfile services/motion_planner/requirements.txt; do
  sed -i '1s/^\xEF\xBB\xBF//' "$f"
done
```

**Done when:** `file services/motion_planner/app.py` reports `UTF-8 Unicode text` (not `UTF-8 Unicode (with BOM)`).

**Push:**
```bash
git add services/motion_planner/app.py services/motion_planner/Dockerfile services/motion_planner/requirements.txt
git commit -m "Ariq-FIX-02: strip UTF-8 BOM from source files"
git push
```

---

## Ibrohim — 7 fixes (≈60 minutes)

Your dispatcher interpolation logic is correct and your unit tests for it are meaningful. But the actuation service has several structural problems, one blocker in the dispatcher, and Ibrohim-06 wasn't done as specified. Read all fixes below before starting — some depend on the same file.

### ☐ Ibrohim-FIX-01 — Write the actuation Dockerfile

**Branch:** `feat/dispatcher-actuation`

**Problem:** `services/actuation/Dockerfile` is **empty**. `docker compose build` will fail.

**Do exactly this:** create `services/actuation/Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/actuation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/actuation /app/services/actuation

ENV PYTHONPATH=/app

EXPOSE 8040

CMD ["uvicorn", "services.actuation.app:app", "--host", "0.0.0.0", "--port", "8040"]
```

Also add `fastapi`, `uvicorn`, `pydantic>=2` to `services/actuation/requirements.txt` — they're needed for FIX-03 (see below).

**Done when:** the file exists and has the content above.

**Push:** commit together with FIX-03 (they're the same service, one rewrite).

---

### ☐ Ibrohim-FIX-02 — Move dispatcher ZMQ bind into a startup handler

**Branch:** `feat/dispatcher-actuation`

**Problem:** in `services/dispatcher/app.py`, this runs at module import:
```python
context = zmq.Context()
socket = context.socket(zmq.PUSH)
socket.bind("tcp://*:5556")
```
Meaning: every time `test_dispatcher.py` imports `app`, it tries to bind port 5556. In CI (or on your machine after the first run), you'll get `zmq.error.ZMQError: Address in use`.

**Do exactly this:** in `services/dispatcher/app.py`, replace the module-level ZMQ setup block with:
```python
context: zmq.Context | None = None
socket: zmq.Socket | None = None


@app.on_event("startup")
def _startup_zmq() -> None:
    global context, socket
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.bind("tcp://*:5556")


@app.on_event("shutdown")
def _shutdown_zmq() -> None:
    global socket, context
    if socket is not None:
        socket.close()
    if context is not None:
        context.term()
```
Everything else in the file stays the same. The socket is only opened when uvicorn boots the app, not on import.

**Done when:** `python -c "from services.dispatcher.app import interpolate"` completes without any network binding.

**Push:**
```bash
git add services/dispatcher/app.py
git commit -m "Ibrohim-FIX-02: bind dispatcher ZMQ on startup, not import"
git push
```

---

### ☐ Ibrohim-FIX-03 — Rewrite actuation as a FastAPI service (fixes 3 things at once)

**Branch:** `feat/dispatcher-actuation`

**Problem — three at once:**
1. Actuation currently connects to `tcp://localhost:5556` — that's dispatcher's frame stream to sim-bridge. ZMQ PUSH/PULL is round-robin, so actuation would **steal every other frame** from the sim. Broken.
2. Actuation publishes to MQTT topic `"robot/joints"`. The contract says `"xlerobot/cmd"`. Wrong topic.
3. `while True:` and `client.connect(...)` run at module import — importing the module hangs forever. No `if __name__ == "__main__"` guard.

**Design decision (agreed with Aiman):** actuation stops being a ZMQ consumer. It becomes an HTTP service on port `8040` with `POST /actuate`. Dispatcher, after all 30 frames are sent, calls `POST http://actuation:8040/actuate` with the final joints. That's the "run validated" signal. Actuation then publishes once to MQTT.

**Do exactly this:** replace `services/actuation/app.py` with:
```python
import json
import os

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException

from services.shared.schemas import ActuationCommand

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = "xlerobot/cmd"

app = FastAPI(title="actuation")

_client: mqtt.Client | None = None


@app.on_event("startup")
def _connect_mqtt() -> None:
    global _client
    _client = mqtt.Client()
    _client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    _client.loop_start()


@app.on_event("shutdown")
def _disconnect_mqtt() -> None:
    if _client is not None:
        _client.loop_stop()
        _client.disconnect()


@app.post("/actuate")
def actuate(cmd: ActuationCommand) -> dict:
    if _client is None:
        raise HTTPException(503, "MQTT client not initialised")
    payload = json.dumps({"joints": cmd.joints})
    result = _client.publish(MQTT_TOPIC, payload)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(502, f"MQTT publish failed: rc={result.rc}")
    return {"published": True, "topic": MQTT_TOPIC}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

Then in `services/dispatcher/app.py`, after the interpolation loop (right before `current_joints = target`), add an HTTP call to actuation:
```python
import httpx  # add to imports at top

ACTUATION_URL = os.environ.get("ACTUATION_URL", "http://actuation:8040/actuate")
# put this at module top:
import os
```
And after the `for frame_id, frame in enumerate(frames): ...` loop:
```python
    # Run validated — trigger actuation
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(ACTUATION_URL, json={"joints": target})
    except httpx.HTTPError as e:
        print(f"[dispatcher] actuation call failed: {e}")

    current_joints = target
```
Add `httpx` to `services/dispatcher/requirements.txt`.

**Done when:**
- Actuation container starts and `GET /health` returns 200
- `POST http://actuation:8040/actuate` with `{"joints":[0,0,0,0,0,0]}` publishes to MQTT topic `xlerobot/cmd`
- Dispatcher, after `/dispatch`, calls actuation exactly once

**Push:**
```bash
git add services/actuation/app.py services/actuation/Dockerfile services/actuation/requirements.txt services/dispatcher/app.py services/dispatcher/requirements.txt
git commit -m "Ibrohim-FIX-03: rewrite actuation as HTTP service on 8040; dispatcher triggers it"
git push
```

---

### ☐ Ibrohim-FIX-04 — Replace test_actuation.py with a real test

**Branch:** `feat/dispatcher-actuation`

**Problem:** the current test only verifies that `Mock()` records calls — it doesn't test any actuation code:
```python
mqtt_client = Mock()
mqtt_client.publish("robot/joints", ...)
mqtt_client.publish.assert_called_once()  # ← this is testing Mock, not you
```

**Do exactly this:** replace `tests/unit/test_actuation.py` with:
```python
import json
from unittest.mock import MagicMock

import services.actuation.app as actuation_app
from fastapi.testclient import TestClient


def test_actuate_publishes_to_correct_topic(monkeypatch):
    fake_client = MagicMock()
    fake_client.publish.return_value.rc = 0  # MQTT_ERR_SUCCESS
    monkeypatch.setattr(actuation_app, "_client", fake_client)

    client = TestClient(actuation_app.app)
    resp = client.post("/actuate", json={"joints": [1, 2, 3, 4, 5, 6]})

    assert resp.status_code == 200
    assert resp.json()["topic"] == "xlerobot/cmd"

    fake_client.publish.assert_called_once()
    topic, payload = fake_client.publish.call_args[0]
    assert topic == "xlerobot/cmd"
    assert json.loads(payload) == {"joints": [1, 2, 3, 4, 5, 6]}


def test_actuate_rejects_wrong_joint_count():
    client = TestClient(actuation_app.app)
    resp = client.post("/actuate", json={"joints": [1, 2, 3]})  # 3 not 6
    assert resp.status_code == 422  # pydantic contract violation
```

**Done when:** `pytest tests/unit/test_actuation.py` — both tests pass.

**Push:**
```bash
git add tests/unit/test_actuation.py
git commit -m "Ibrohim-FIX-04: replace mock-only test with real actuation test"
git push
```

---

### ☐ Ibrohim-FIX-05 — Pull latest contracts skeleton from feat/integration

**Branch:** `feat/dispatcher-actuation`

**Problem:** your branch never picked up A-03 (the `contracts/interface-contracts.md` skeleton). Without it, FIX-06 has nothing to edit.

**Do exactly this:**
```bash
git fetch origin
git merge origin/feat/integration
```
Resolve any conflicts on `contracts/.gitkeep` / `sim/.gitkeep` by accepting the incoming deletion (those files should NOT exist). Accept the incoming `sim/extension.py` (Aiman's pointer file). Accept the incoming `contracts/interface-contracts.md` (the A-03 skeleton).

**Done when:** `ls contracts/interface-contracts.md` exists on your branch and starts with `# Interface Contracts`.

**Push:**
```bash
git push
```
(the merge commit is fine — no separate commit needed)

---

### ☐ Ibrohim-FIX-06 — Fill your two contract rows (the real Ibrohim-06)

**Branch:** `feat/dispatcher-actuation`

**Problem:** your original Ibrohim-06 was supposed to fill contract rows but you did something else. Now that FIX-05 gave you the skeleton, fill in your two sections.

**Do exactly this:** in `contracts/interface-contracts.md`, find the sections `## dispatcher → sim-bridge` and `## actuation → mosquitto`. Fill in:

For **dispatcher → sim-bridge** (owner: Ibrohim):
```
**Payload example:**
```json
{"joints": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "frame_id": 12}
```

**Initiated:** when POST /dispatch is accepted with a valid joints target

**Concluded:** after 30 frames are sent over ZMQ PUSH on tcp://*:5556

**Error modes:** if sim-bridge is not connected, PUSH buffers frames; if buffer fills, dispatcher blocks. No error is returned to the caller of POST /dispatch (fire-and-forget).
```

For **actuation → mosquitto** (owner: Ibrohim):
```
**Payload example:**
```json
{"joints": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
```

**Initiated:** when dispatcher POSTs to actuation's /actuate endpoint after a run's interpolation completes

**Concluded:** when MQTT broker acknowledges the publish (rc == 0)

**Error modes:** returns HTTP 502 if MQTT publish fails; HTTP 503 if MQTT client not initialised; HTTP 422 if joints array is not exactly 6 floats.
```

**Done when:** both sections have the fields above and no `_tbd_` placeholders remain in them.

**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "Ibrohim-FIX-06: fill dispatcher and actuation contract rows"
git push
```

---

## Summary of push order

**Ariq:**
1. Ariq-FIX-01 (Dockerfile)
2. Ariq-FIX-02 (BOM strip)

**Ibrohim:**
1. Ibrohim-FIX-01 + FIX-03 together (Dockerfile + actuation rewrite, one commit)
2. Ibrohim-FIX-02 (dispatcher startup handler)
3. Ibrohim-FIX-04 (test rewrite)
4. Ibrohim-FIX-05 (pull integration)
5. Ibrohim-FIX-06 (contract rows)

When done, message Aiman and Aiman will run the sprint-1 group merge (A-05).
