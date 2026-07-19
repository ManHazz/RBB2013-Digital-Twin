# XLeRobot Digital Twin — Deployment & Dev-Practices Execution Plan

**For:** RBB2013 Digital Twin final project — *Project Deployment (5%)* + *Project Development Practices (5%)*
**Goal:** Refactor the existing XLeRobot pipeline into containerized microservices with documented interface contracts, persistence, a full test suite, and CI/CD — without rewriting the working IK/LLM/sim logic.
**Driver:** This file is written for Claude Code. Execute phase by phase. Each phase names the rubric line it satisfies. Do not skip the contract/test/CI phases — those are where the marks are.

---

## 0. Assumptions (correct these before starting)

- The existing code exists in this repo: `llm_controller.py`, `robot_ik.py`, `extension.py`, `grasp_test.py` (+ interpolator logic). If paths differ, adapt.
- `extension.py` runs **on the host inside NVIDIA Omniverse** and **cannot be containerized** (GPU + Kit runtime). It stays on the host and talks to containers over ZMQ. This boundary is documented deliberately, not a gap.
- Ollama runs on the host (or its own container) with GPU access; services reach it over HTTP.
- Team vs solo: the sprint / group-merge story below assumes a real git history exists. If solo, Claude Code still creates the branch/tag/sprint-doc structure, but the "group merge" evidence must come from real commits — flag this rather than fabricate contributors.

---

## 1. Target architecture (the microservice decomposition)

Carve the monolith into these services. Each becomes its own container (except the sim bridge).

| # | Service | Was | Responsibility | Interface in | Interface out |
|---|---------|-----|----------------|--------------|---------------|
| 1 | `nl-command` | `llm_controller.py` | Take text, call Ollama, return target pose. Entry orchestrator. | HTTP `POST /command` :8010 | HTTP → planner |
| 2 | `motion-planner` | `robot_ik.py` | IK solve + reachability + collision check | HTTP `POST /plan` :8020 | HTTP → dispatcher |
| 3 | `dispatcher` | interpolator | 30fps interpolation, stream joint frames to sim | HTTP `POST /dispatch` :8030 | ZMQ PUSH :5556 |
| 4 | `sim-bridge` | `extension.py` | Apply joints in Omniverse, publish live state | ZMQ PULL :5556 | ZMQ PUB :5557 |
| 5 | `telemetry` | (new middleware) | Subscribe to sim state, write history + latest state | ZMQ SUB :5557 | SQL → TimescaleDB, cache → Redis |
| 6 | `actuation` | MQTT publisher | On validated run, publish command to physical robot | internal trigger | MQTT PUB :1883 |
| — | `ollama` | infra | LLM inference | HTTP :11434 | — |
| — | `timescaledb` | infra | Time-series persistence | SQL :5432 | — |
| — | `redis` | infra | Latest-state cache (proves state persistence) | :6379 | — |
| — | `mosquitto` | infra | MQTT broker | :1883 | — |
| — | `grafana` | infra | Visualization from TimescaleDB | :3000 | — |

**Flow:** `client → nl-command → motion-planner → dispatcher → (ZMQ) sim-bridge → (ZMQ) telemetry → DB/cache → grafana`, with `actuation` firing MQTT once a run is validated.

---

## 2. Target repo layout

```
xlerobot-dt/
├── services/
│   ├── nl_command/      { app.py, Dockerfile, requirements.txt }
│   ├── motion_planner/  { app.py (imports robot_ik), Dockerfile, requirements.txt }
│   ├── dispatcher/      { app.py, Dockerfile, requirements.txt }
│   ├── telemetry/       { app.py, Dockerfile, requirements.txt }
│   ├── actuation/       { app.py, Dockerfile, requirements.txt }
│   └── shared/          { schemas.py — pydantic models = the contract types }
├── sim/
│   └── extension.py     # host-side, documented as non-containerized
├── infra/
│   ├── docker-compose.yml
│   ├── mosquitto/mosquitto.conf
│   ├── timescaledb/init.sql
│   └── grafana/ (provisioning + dashboard json)
├── tests/
│   ├── unit/            # per-service pure logic (IK math, collision, prompt parse)
│   ├── integration/     # service-to-service over the real contract
│   └── system/          # full pipeline end-to-end
├── contracts/
│   └── interface-contracts.md
├── .github/workflows/ci.yml
├── docs/
│   ├── ARCHITECTURE.md
│   └── SPRINT_LOG.md
├── PLAN.md
└── README.md
```

---

## Execution phases (run in this order — front-loaded for the 19 July deadline)

### Phase A — Scaffold + extract (do first)
- Create the repo layout above. `git init` if not already versioned.
- Move `robot_ik.py` into `services/motion_planner/` and expose it behind a FastAPI `POST /plan`. **Do not modify the IK math** — wrap it.
- Wrap `llm_controller.py`'s Ollama call as `nl-command` `POST /command`.
- Extract the interpolator into `dispatcher` `POST /dispatch` that produces frames and ZMQ-pushes them.
- Define shared request/response models in `services/shared/schemas.py` (these become your contract types).
- **Rubric:** *Deployment — "well defined microservices and specify exactly the function of each."*

### Phase B — Interface contracts (high marks, low effort)
Write `contracts/interface-contracts.md`. For **every pair** of communicating services, a row with: route/topic, port, protocol, data format, when initiated, when concluded. Start from this table and fill payload schemas:

| From → To | Route/Topic | Port | Protocol | Data format | Initiated | Concluded |
|-----------|-------------|------|----------|-------------|-----------|-----------|
| client → nl-command | `POST /command` | 8010 | HTTP/JSON | `{text}` → `{target:{x,y,z}}` | user submits text | pose returned |
| nl-command → ollama | `POST /api/generate` | 11434 | HTTP/JSON | prompt → completion | on each command | completion returned |
| nl-command → motion-planner | `POST /plan` | 8020 | HTTP/JSON | `{target}` → `{joints[6],reachable,collision_free}` | pose resolved | plan returned |
| motion-planner → dispatcher | `POST /dispatch` | 8030 | HTTP/JSON | `{joints[6]}` → `{accepted}` | plan valid | ack |
| dispatcher → sim-bridge | frames | 5556 | ZMQ PUSH/PULL | `{joints[6],frame_id}` | dispatch accepted | last frame sent |
| sim-bridge → telemetry | state | 5557 | ZMQ PUB/SUB | `{joints[6],ee_pose,ts}` | sim tick | run ends |
| telemetry → timescaledb | insert | 5432 | SQL | hypertable rows | on each state msg | commit |
| telemetry → redis | latest state | 6379 | RESP | `state:latest` key | on each state msg | overwritten |
| actuation → mosquitto | `xlerobot/cmd` | 1883 | MQTT/JSON | `{joints[6]}` | run validated | publish ack |
| grafana → timescaledb | query | 5432 | SQL | time-series read | dashboard refresh | rows returned |

- **Rubric:** *Deployment — "contract information which states the route, port, protocol format and data format exchange between every pair of microservices and when that communication is initiated and concluded."* This table maps 1:1 to that sentence — hit every pair.

### Phase C — Containerize + compose
- One `Dockerfile` per service (slim python base, copy requirements, copy code, `uvicorn`/entrypoint).
- `infra/docker-compose.yml` wiring all services + infra (ollama optional as container or host via `host.docker.internal`). Named volumes for `timescaledb` and `redis`.
- Prove it comes up: `docker compose up` → all healthy → one command flows end-to-end (sim-bridge target is the host Omniverse over ZMQ).
- **Rubric:** *Deployment — "Build containers for each microservices, demonstrate successful deployment."*

### Phase D — Persistence proof
- `infra/timescaledb/init.sql`: create hypertable `robot_state(ts, joints, ee_pose)`.
- After a run, `docker compose restart timescaledb redis` → re-query → data survives → screenshot/log it.
- `telemetry` writes latest state to Redis; show state restored after restart.
- **Rubric:** *Deployment — "Prove that the data captured and stored by the microservices is persistent" + "persistence in data and state storage."* Note the two halves: **data** (TimescaleDB history) and **state** (Redis latest) — cover both explicitly.

### Phase E — Test suite (unit → integration → system)
- **unit/**: `robot_ik` forward+inverse round-trip (assert < tolerance), collision-checker true/false cases, prompt→pose parse. Include deliberate **fail cases** (unreachable target, colliding target) asserting the service rejects them.
- **integration/**: spin two services, hit the real contract (e.g. planner rejects unreachable target with correct schema), MQTT publish→subscribe round-trip.
- **system/**: compose up, send a command, assert a row lands in TimescaleDB with expected joints.
- Use `pytest`; mark tiers so CI can run them in stages.
- **Rubric:** *Deployment — "complete test suite to test ... microservices, interface and overall digital twin system operation."* + *Dev Practices — "Unit and interface/integration tests ... demonstrated pass and fail cases" + "system tests."* The explicit **pass AND fail cases** are graded — make failures assert the right rejection, not just crash.

### Phase F — CI/CD + regression
- `.github/workflows/ci.yml`: on push/PR → install → **lint → unit → integration** (docker compose for service pairs). Fail the build on any red.
- Add a **regression job**: a fixed set of golden command→joint expectations that must not drift; runs on every push.
- Optional CD step: on green `main`, `docker compose build` + tag images (an "automatic deployment" gesture that satisfies the skilled tier without needing a real registry).
- **Rubric:** *Dev Practices — "Updates are to be triggered by automatic build and application of regression test suite (CI/CD principles)" + "automatic deployment & regression test."*

### Phase G — Scaling demo
- Make one stateless service (e.g. `motion-planner`) horizontally scalable: `docker compose up --scale motion-planner=3` behind a lightweight round-robin (nginx or compose's built-in DNS).
- Show it serving under concurrent requests.
- **Rubric:** *Deployment — "demonstrate successful deployment and scaling of microservices" + "scaling of the microservices."* Scaling is the difference between Competent (4) and Skilled (5) — don't skip it.

### Phase H — Sprint + version-control evidence
- `docs/SPRINT_LOG.md`: document **≥2 sprint cycles** — sprint goal, per-member tasks, deliverables, what merged at sprint end. Back it with real git: tag `sprint-1`, `sprint-2`; feature branches per module merged via PR into `main` at each sprint boundary.
- If solo: still tag sprints and use PR merges, but be honest in the doc — do not invent teammates. If team: ensure each member has real authored commits and a group merge at each sprint end.
- **Rubric:** *Dev Practices — "sprint planning and execution ... over at least 2 sprint cycles and consistent version control of individual and group merge at the end of sprint" + "for all modules of the system."* "All modules" + "group merge" is the Skilled bar.

---

## Suggested order under time pressure (due today)

1. **Phase B** (contracts doc) — highest marks per hour, needs no working code.
2. **Phase A + C** — extract + containerize + compose up.
3. **Phase E** (tests, incl. fail cases) + **Phase F** (CI) — these two carry both rubrics.
4. **Phase D** (persistence proof) + **Phase G** (scaling) — pushes Deployment to Skilled.
5. **Phase H** (sprint doc + tags) — mostly documentation over your real git history.

## How to drive Claude Code through this
- Give it this file and say: *"Execute Phase A, then stop and show me `docker compose up` output before Phase C."* Gate each phase so you can verify the demo still runs.
- Keep `extension.py` untouched except the ZMQ endpoint config — the sim is your demo and you don't want to break it the day it's due.
- Capture a screenshot/log at each phase's "prove it" step — that evidence is what you submit, not just the code.
