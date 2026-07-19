# XLeRobot Digital Twin — Atomic Task List (Group of 5)

## How to use this file

Your branch is already created on GitHub — you just need to work in it.

### One-time setup (do this once)

```bash
git clone https://github.com/ManHazz/RBB2013-Digital-Twin.git
cd RBB2013-Digital-Twin
git checkout <your-branch>          # e.g. feat/nl-command — see your section below
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
```

### For each task block below

**If you have Claude Code CLI:** paste the whole task block into Claude Code — it will create files, run checks, and push automatically.

**If you're on Gemini Pro / Claude web / any chat LLM:** follow this drill for each task:

1. **Give the LLM context first.** Open your chat and paste this so it knows the shared contract types:

   ```
   In this project, all services share these pydantic v2 types from
   services/shared/schemas.py — do not invent new field names:

   [paste the contents of services/shared/schemas.py here]
   ```

2. **Paste the task block** (e.g. "Bento-01" — the whole thing including *Do exactly this*, *Done when*, *Push*).

3. **Add this instruction at the end of your chat message:**

   ```
   Generate every file described in the task. For each file, output
   its full path as a header, then its complete contents in a fenced
   code block, so I can copy each one verbatim into my editor.
   ```

4. **Save each file** the LLM produces to the exact path shown.

5. **Run the "Done when" check** yourself in your terminal. If it fails, paste the error back into the chat and ask the LLM to fix it, then re-save.

6. **Run the `Push` commands** from the task block in your terminal.

### Rules

- **Do tasks in order** within your section. A *Preconditions* line names what must be done first (yours or someone else's).
- **One task = one commit = one push.** Don't batch multiple tasks into a single commit.
- **Never edit `services/shared/schemas.py`** — that's Aiman's frozen contract. If you think a field is wrong, message Aiman.
- **Sprint 2 tasks will be added after Sprint 1 lands.** Do not skip ahead.

---

## The one rule that makes this parallel

**The contract is frozen before anyone builds.** Task **A-02** locks `services/shared/schemas.py`. After that, every service just imports from it. If the schema must change mid-sprint, Aiman announces it and bumps a version note in the file. Nobody else edits `schemas.py`.

## Git workflow (the version-control mark)

- Each teammate works on their **own feature branch**. Never push to `main`.
- Every task ends with a `git commit` + `git push` — one task = one commit.
- **Sprint end = group merge day:** Aiman opens PRs into `main`, all get reviewed, all merged together, then tag `sprint-1`.
- Everyone must have real authored commits in **both** sprints.

---

## Aiman (lead) — branch `feat/integration`

### ☐ A-01 — Scaffold repo layout
**Preconditions:** none
**Do exactly this:**
1. Create these directories (empty for now): `services/nl_command/`, `services/motion_planner/`, `services/dispatcher/`, `services/actuation/`, `services/telemetry/`, `services/shared/`, `sim/`, `infra/mosquitto/`, `infra/timescaledb/`, `infra/grafana/`, `tests/unit/`, `tests/integration/`, `tests/system/`, `contracts/`, `.github/workflows/`, `docs/`.
2. Add a `.gitkeep` file inside each empty directory.
3. Create empty `docs/ARCHITECTURE.md` and `docs/SPRINT_LOG.md`.
**Done when:** `tree -L 2` shows the layout from `PLAN.md` section 2.
**Push:**
```bash
git checkout -b feat/integration
git add .
git commit -m "A-01: scaffold repo layout"
git push -u origin feat/integration
```

### ☐ A-02 — Lock shared schemas
**Preconditions:** A-01 done
**Do exactly this:** Create `services/shared/schemas.py` with pydantic v2 models:
- `CommandRequest(text: str)`
- `TargetPose(x: float, y: float, z: float)`
- `PlanRequest(target: TargetPose)`
- `PlanResponse(joints: list[float], reachable: bool, collision_free: bool)` — `joints` must be exactly 6 floats
- `DispatchRequest(joints: list[float])`
- `DispatchResponse(accepted: bool)`
- `SimState(joints: list[float], ee_pose: TargetPose, ts: float)`
- `ActuationCommand(joints: list[float])`

Add a top-of-file comment: `# CONTRACT — do not edit without Aiman's approval. Version: 1.0`.
**Done when:** `python -c "from services.shared.schemas import *"` succeeds.
**Push:**
```bash
git add services/shared/schemas.py
git commit -m "A-02: lock shared contract schemas v1.0"
git push
```

### ☐ A-03 — Interface contracts skeleton
**Preconditions:** A-02 done
**Do exactly this:** Create `contracts/interface-contracts.md`. Copy the table from `PLAN.md` Phase B into it verbatim. Under the table, add one heading per row (e.g., `## client → nl-command`) with an empty payload example block. M2–M5 will fill in their rows in their own tasks.
**Done when:** file exists with the full table and 10 empty section stubs.
**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "A-03: interface contracts skeleton"
git push
```

### ☐ A-04 — Move sim/extension.py in
**Preconditions:** A-01 done
**Do exactly this:** Move the existing `extension.py` from the repo root into `sim/extension.py`. Do not modify its logic. If it references ZMQ endpoints, ensure it PULLs on `tcp://*:5556` and PUBs on `tcp://*:5557`. Add a header comment: `# Runs on host inside Omniverse — not containerized. See PLAN.md §0.`
**Done when:** file lives at `sim/extension.py` and ZMQ ports match the contract.
**Push:**
```bash
git add sim/extension.py
git rm extension.py 2>/dev/null || true
git commit -m "A-04: move extension.py to sim/, align ZMQ ports"
git push
```

### ☐ A-05 — Open PR for sprint-1 branch
**Preconditions:** A-01..A-04 done, plus all M2–M5 sprint-1 tasks pushed
**Do exactly this:** Open a GitHub PR from `feat/integration` → `main` titled "Sprint 1 — integration + contract". In the PR body, link the other teammates' PRs. Do not merge yet — wait for group merge day.
**Push:**
```bash
gh pr create --title "Sprint 1 — integration + contract" --body "See linked PRs from Bento, Ariq, Ibrohim, Raziq. Group merge on sprint-1 tag day."
```

---

## Bento (NL Command) — branch `feat/nl-command`

### ☐ Bento-01 — Scaffold nl_command service
**Preconditions:** A-02 done (schemas exist)
**Do exactly this:** Create `services/nl_command/app.py`, `services/nl_command/Dockerfile`, `services/nl_command/requirements.txt`.
- `requirements.txt`: `fastapi`, `uvicorn`, `httpx`, `pydantic>=2`
- `app.py`: a FastAPI app that imports `CommandRequest`, `TargetPose` from `services.shared.schemas` and defines `POST /command` returning a hardcoded `TargetPose(x=0, y=0, z=0)` for now (real Ollama call in Bento-02).
- `Dockerfile`: `python:3.11-slim`, copy requirements, `pip install`, copy code, `CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]`.
**Done when:** `docker build -t nl-command services/nl_command/` succeeds and `uvicorn` starts locally.
**Push:**
```bash
git checkout -b feat/nl-command
git add services/nl_command/
git commit -m "Bento-01: scaffold nl_command FastAPI service"
git push -u origin feat/nl-command
```

### ☐ Bento-02 — Wire Ollama call
**Preconditions:** Bento-01 done
**Do exactly this:** In `services/nl_command/app.py`, replace the hardcoded pose with an `httpx.AsyncClient` call to `POST http://{OLLAMA_HOST}/api/generate` (env var `OLLAMA_HOST`, default `host.docker.internal:11434`). Parse the completion into a `TargetPose`. If the completion cannot be parsed into 3 floats, raise `HTTPException(422, "cannot parse pose from LLM response")`. Reuse the parsing logic from the original `llm_controller.py` if applicable.
**Done when:** hitting `POST /command` with `{"text":"pick up the block"}` returns a valid `TargetPose`.
**Push:**
```bash
git add services/nl_command/app.py
git commit -m "Bento-02: wire Ollama call in POST /command"
git push
```

### ☐ Bento-03 — Unit test: happy path
**Preconditions:** Bento-02 done
**Do exactly this:** Create `tests/unit/test_nl_command.py`. Use `pytest` + `httpx.MockTransport` (or `respx`) to stub Ollama's response as `"1.0 2.0 3.0"`. Assert `POST /command` with `{"text":"go here"}` returns HTTP 200 and `{"x":1.0,"y":2.0,"z":3.0}`.
**Done when:** `pytest tests/unit/test_nl_command.py::test_happy_path` passes.
**Push:**
```bash
git add tests/unit/test_nl_command.py
git commit -m "Bento-03: unit test — nl_command happy path"
git push
```

### ☐ Bento-04 — Unit test: fail case
**Preconditions:** Bento-03 done
**Do exactly this:** In the same test file, add `test_empty_text_returns_422` (input `{"text":""}` → HTTP 422) and `test_garbled_ollama_returns_422` (Ollama returns `"gibberish nonsense"` → HTTP 422).
**Done when:** both fail-case tests pass.
**Push:**
```bash
git add tests/unit/test_nl_command.py
git commit -m "Bento-04: unit test — nl_command fail cases (empty, garbled)"
git push
```

### ☐ Bento-05 — Fill contract rows
**Preconditions:** A-03 done, Bento-02 done
**Do exactly this:** In `contracts/interface-contracts.md`, fill in the three sections owned by nl-command: `## client → nl-command`, `## nl-command → ollama`, `## nl-command → motion-planner`. Each section: payload example (real JSON), when initiated, when concluded, error modes.
**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "Bento-05: fill nl-command contract rows"
git push
```

---

## Ariq (Motion Planner) — branch `feat/motion-planner`

### ☐ Ariq-01 — Scaffold motion_planner service
**Preconditions:** A-02 done
**Do exactly this:** Move the existing `robot_ik.py` from the repo root into `services/motion_planner/robot_ik.py` — **do not change one line of the IK math**. Create `services/motion_planner/app.py`, `Dockerfile`, `requirements.txt`.
- `requirements.txt`: `fastapi`, `uvicorn`, `numpy`, `pydantic>=2` (plus whatever `robot_ik.py` needs)
- `app.py`: FastAPI app importing `PlanRequest`, `PlanResponse` from `services.shared.schemas`. `POST /plan` returns `PlanResponse(joints=[0]*6, reachable=True, collision_free=True)` for now.
- `Dockerfile`: slim python, port 8020.
**Done when:** container builds and `uvicorn` starts.
**Push:**
```bash
git checkout -b feat/motion-planner
git add services/motion_planner/
git rm robot_ik.py 2>/dev/null || true
git commit -m "Ariq-01: scaffold motion_planner service, move robot_ik.py"
git push -u origin feat/motion-planner
```

### ☐ Ariq-02 — Wire robot_ik into /plan
**Preconditions:** Ariq-01 done
**Do exactly this:** In `app.py`, call the IK solve function from `robot_ik` with the incoming target. Populate `joints`, set `reachable=False` if IK fails to converge, set `collision_free=False` if the collision check (already in `robot_ik.py`) returns a collision. **Do not modify `robot_ik.py`.**
**Done when:** `POST /plan` with `{"target":{"x":0.3,"y":0,"z":0.3}}` returns 6 joints and both flags.
**Push:**
```bash
git add services/motion_planner/app.py
git commit -m "Ariq-02: wire robot_ik into POST /plan"
git push
```

### ☐ Ariq-03 — Unit test: IK round-trip
**Preconditions:** Ariq-02 done
**Do exactly this:** Create `tests/unit/test_motion_planner.py`. Test: given a reachable target `T`, call `/plan`, take the returned joints, run forward kinematics from `robot_ik`, assert the resulting EE pose is within `1e-3` of `T`.
**Done when:** test passes.
**Push:**
```bash
git add tests/unit/test_motion_planner.py
git commit -m "Ariq-03: unit test — IK forward/inverse round-trip"
git push
```

### ☐ Ariq-04 — Unit test: unreachable rejected
**Preconditions:** Ariq-03 done
**Do exactly this:** Add `test_unreachable_target_rejected`. Send a target obviously outside the arm's reach (e.g., `{"x":10,"y":10,"z":10}`). Assert response returns `reachable=False`. The service must return HTTP 200 (not 500) — this is a *valid* answer, just a negative one.
**Done when:** test passes.
**Push:**
```bash
git add tests/unit/test_motion_planner.py
git commit -m "Ariq-04: unit test — unreachable target rejected"
git push
```

### ☐ Ariq-05 — Unit test: colliding rejected
**Preconditions:** Ariq-04 done
**Do exactly this:** Add `test_colliding_target_rejected`. Send a target known to force a self-collision (pick coordinates that trigger the collision checker in `robot_ik.py`). Assert `collision_free=False`.
**Done when:** test passes.
**Push:**
```bash
git add tests/unit/test_motion_planner.py
git commit -m "Ariq-05: unit test — colliding target rejected"
git push
```

### ☐ Ariq-06 — Fill contract rows
**Preconditions:** A-03 done, Ariq-02 done
**Do exactly this:** In `contracts/interface-contracts.md`, fill in `## nl-command → motion-planner` (input side) and `## motion-planner → dispatcher` (output side).
**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "Ariq-06: fill motion-planner contract rows"
git push
```

---

## Ibrohim (Dispatcher + Actuation) — branch `feat/dispatcher-actuation`

### ☐ Ibrohim-01 — Scaffold dispatcher service
**Preconditions:** A-02 done
**Do exactly this:** Create `services/dispatcher/app.py`, `Dockerfile`, `requirements.txt` (`fastapi`, `uvicorn`, `pyzmq`, `pydantic>=2`). `POST /dispatch` accepts `DispatchRequest`, returns `DispatchResponse(accepted=True)`. Port 8030. Dockerfile publishes port 8030 and exposes 5556 for ZMQ.
**Done when:** container builds; `uvicorn` starts.
**Push:**
```bash
git checkout -b feat/dispatcher-actuation
git add services/dispatcher/
git commit -m "Ibrohim-01: scaffold dispatcher service"
git push -u origin feat/dispatcher-actuation
```

### ☐ Ibrohim-02 — Interpolate + ZMQ push
**Preconditions:** Ibrohim-01 done
**Do exactly this:** In `app.py`, on `POST /dispatch`: read current joints from a module-level cache (init to `[0]*6`), linearly interpolate from current → target at 30 fps over 1 second (30 frames), and `zmq.PUSH` each frame `{"joints":[...], "frame_id":i}` on `tcp://*:5556`. Update the cache to the target after sending. Reuse interpolator logic from the original codebase if it exists.
**Done when:** running the service and hitting `/dispatch` with a target results in 30 frames received on a test ZMQ PULL socket.
**Push:**
```bash
git add services/dispatcher/app.py
git commit -m "Ibrohim-02: interpolate to 30fps and ZMQ PUSH frames"
git push
```

### ☐ Ibrohim-03 — Unit test: frame count
**Preconditions:** Ibrohim-02 done
**Do exactly this:** Create `tests/unit/test_dispatcher.py`. Spin up a ZMQ PULL socket in a background thread, call the dispatcher's interpolate+push function directly (not via HTTP), assert exactly 30 frames received, assert first frame's joints equal start and last frame's joints equal target within `1e-6`.
**Done when:** test passes.
**Push:**
```bash
git add tests/unit/test_dispatcher.py
git commit -m "Ibrohim-03: unit test — dispatcher frame count and endpoints"
git push
```

### ☐ Ibrohim-04 — Scaffold actuation service
**Preconditions:** A-02 done
**Do exactly this:** Create `services/actuation/app.py`, `Dockerfile`, `requirements.txt` (`paho-mqtt`, `pydantic>=2`). Expose a function `publish(ActuationCommand)` that connects to MQTT broker (env `MQTT_HOST`, default `mosquitto:1883`) and publishes JSON to topic `xlerobot/cmd`. No HTTP surface needed — this is a library-style service triggered internally.
**Done when:** container builds.
**Push:**
```bash
git add services/actuation/
git commit -m "Ibrohim-04: scaffold actuation MQTT publisher"
git push
```

### ☐ Ibrohim-05 — Unit test: MQTT pub/sub round-trip
**Preconditions:** Ibrohim-04 done
**Do exactly this:** Create `tests/unit/test_actuation.py`. Use an in-process MQTT broker (`amqtt` or the mosquitto container via `pytest-docker`) — simplest option: spin `mosquitto` in a Docker container fixture. Publish a `ActuationCommand(joints=[1,2,3,4,5,6])`, subscribe from the test, assert the payload arrives on `xlerobot/cmd` matching the sent joints.
**Done when:** test passes.
**Push:**
```bash
git add tests/unit/test_actuation.py
git commit -m "Ibrohim-05: unit test — MQTT pub/sub round-trip"
git push
```

### ☐ Ibrohim-06 — Fill contract rows
**Preconditions:** A-03 done, Ibrohim-02 & Ibrohim-04 done
**Do exactly this:** In `contracts/interface-contracts.md`, fill `## dispatcher → sim-bridge` and `## actuation → mosquitto`.
**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "Ibrohim-06: fill dispatcher and actuation contract rows"
git push
```

---

## Raziq (Telemetry + Observability) — branch `feat/telemetry-observability`

### ☐ Raziq-01 — TimescaleDB init
**Preconditions:** A-01 done
**Do exactly this:** Create `infra/timescaledb/init.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE robot_state (
    ts        TIMESTAMPTZ NOT NULL,
    joints    DOUBLE PRECISION[] NOT NULL,
    ee_x      DOUBLE PRECISION NOT NULL,
    ee_y      DOUBLE PRECISION NOT NULL,
    ee_z      DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('robot_state', 'ts');
```
**Push:**
```bash
git checkout -b feat/telemetry-observability
git add infra/timescaledb/init.sql
git commit -m "Raziq-01: TimescaleDB init — robot_state hypertable"
git push -u origin feat/telemetry-observability
```

### ☐ Raziq-02 — Scaffold telemetry service
**Preconditions:** A-02 done, Raziq-01 done
**Do exactly this:** Create `services/telemetry/app.py`, `Dockerfile`, `requirements.txt` (`pyzmq`, `psycopg[binary]`, `redis`, `pydantic>=2`). `app.py` connects to Timescale (env `PG_DSN`) and Redis (env `REDIS_URL`), then ZMQ SUBs on `tcp://sim-bridge:5557` (env `SIM_STATE_ADDR`). No HTTP surface — daemon-style.
**Push:**
```bash
git add services/telemetry/
git commit -m "Raziq-02: scaffold telemetry service"
git push
```

### ☐ Raziq-03 — Write to Timescale + Redis
**Preconditions:** Raziq-02 done
**Do exactly this:** In `app.py`, for each incoming `SimState` message: insert a row into `robot_state` AND `SET state:latest` in Redis to the JSON of the message. Wrap in a `while True` loop with a try/except that logs and continues.
**Push:**
```bash
git add services/telemetry/app.py
git commit -m "Raziq-03: telemetry writes to Timescale and Redis"
git push
```

### ☐ Raziq-04 — Unit test: Timescale insert/read
**Preconditions:** Raziq-03 done
**Do exactly this:** Create `tests/unit/test_telemetry.py`. Use `pytest-docker` or `testcontainers` to spin a TimescaleDB container with `init.sql` applied. Call the telemetry insert function with a fake `SimState`, then `SELECT` and assert the row is present with matching joints.
**Push:**
```bash
git add tests/unit/test_telemetry.py
git commit -m "Raziq-04: unit test — Timescale insert/read"
git push
```

### ☐ Raziq-05 — Unit test: Redis latest state
**Preconditions:** Raziq-04 done
**Do exactly this:** Add `test_redis_latest_state` in the same file. Spin a Redis container, write a `SimState`, read `state:latest`, assert JSON matches. Then write a second `SimState` and assert `state:latest` reflects the newer one (overwrite semantics).
**Push:**
```bash
git add tests/unit/test_telemetry.py
git commit -m "Raziq-05: unit test — Redis latest state overwrite"
git push
```

### ☐ Raziq-06 — Fill contract rows
**Preconditions:** A-03 done, Raziq-03 done
**Do exactly this:** Fill `## sim-bridge → telemetry`, `## telemetry → timescaledb`, `## telemetry → redis` in `contracts/interface-contracts.md`.
**Push:**
```bash
git add contracts/interface-contracts.md
git commit -m "Raziq-06: fill telemetry contract rows"
git push
```

---

## Sprint 1 done — group merge

When every task above is checked off:
1. Aiman verifies each teammate has an open PR into `main`.
2. Group reviews PRs together.
3. Merge all in one session.
4. Tag: `git tag sprint-1 && git push --tags`.
5. Aiman appends a sprint-1 entry to `docs/SPRINT_LOG.md` (goal, who merged what, what shipped).

**Sprint 2 tasks will be written after sprint-1 is tagged.** They cover: `docker-compose.yml` wiring, CI pipeline, persistence proof, scaling demo, Grafana dashboard, regression tests, system test.
