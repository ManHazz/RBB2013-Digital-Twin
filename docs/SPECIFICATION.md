# XLeRobot Digital Twin — Specification & Plan

**Course:** RBB2013 Digital Twin (May 2026)
**Team:** Aiman (lead), Bento, Ariq, Ibrohim, Raziq
**Rubric:** Project Specification & Plan (5%)

---

## 1. Problem statement

Robot arms in industrial and lab settings are typically driven by low-level joint commands scripted by engineers. This makes them:
- **Inaccessible** to non-programmer operators who understand the *task* but not the joint math.
- **Slow to iterate** — every new task requires new joint scripts, new safety checks, new visual verification.
- **Opaque during operation** — no live insight into the arm's actual joint state, end-effector pose, or task progress.

## 2. Purpose and SMART outcome

A digital twin of a 6-DoF robot arm that lets a non-programmer operator command the physical robot in **natural language**, verify the motion **in simulation before execution**, and observe **live telemetry** of every attempted move.

**SMART outcome:** Given a user's plain-English command (e.g. "pick up the ball"), the digital twin shall
- **Specific:** resolve the command to a target end-effector pose using an LLM,
- **Measurable:** produce 6 joint angles within ±1e-3 radian of the target's inverse kinematics solution,
- **Achievable:** stream the interpolated motion to an Omniverse simulation at 30 fps,
- **Relevant:** publish the validated joint command to the physical robot over MQTT,
- **Time-bound:** complete the full loop (command → sim frame received → row in TimescaleDB) within **10 seconds**, verified by an automated system test (`tests/system/test_end_to_end.py`).

## 3. Digital twin state

The **live state** of the digital twin at any instant consists of:

| State component | Source | Storage |
|----|----|----|
| **6 joint angles** (radians) | Omniverse sim tick (extension.py) | Redis key `state:latest` + TimescaleDB `robot_state.joints` |
| **End-effector pose** (x, y, z, cm) | Forward kinematics on joints | Same |
| **Target ball position** (x, y, z, cm) | Fixed in extension.py; part of published state | Same |
| **Obstacle positions** (per-obstacle x, y, z, r) | Fixed in extension.py; part of published state | Same |
| **Timestamp** (`ts`) | Publisher wall clock | TimescaleDB partition key |

**Latest state** — Redis `state:latest` key, overwritten every ~100 ms.
**Historical state** — TimescaleDB `robot_state` hypertable, one row per publish tick.

## 4. Data streams (all real, from a live simulation loop)

Multiple real data streams originate at the Omniverse sim-bridge and are aggregated into digital twin state by the `telemetry` service:

1. **Joint state stream** — sim-bridge publishes joint angles at 10 Hz over ZMQ PUB on port 5557.
2. **End-effector pose stream** — derived per-tick from forward kinematics on the joint angles.
3. **Scene object stream** — target ball + obstacles published alongside joint state (positions can drift if edited in the extension).
4. **Command trigger stream** — user commands enter via `POST /command` → LLM → planner → dispatcher, forming an event-driven upstream stream.

**Aggregation:** `telemetry` service subscribes to sim-bridge's ZMQ topic, decodes each JSON message into a `SimState` pydantic model, writes one row per message to TimescaleDB (append-only historical stream) AND overwrites Redis `state:latest` (aggregate latest snapshot).

## 5. Visualization and measure of success

Two visualizations proving the digital twin works end-to-end:

1. **Omniverse Kit viewport** — 3D scene with robot arm, target ball, obstacles. Robot arm animates in real time as joint commands stream in from the dispatcher. This is the "physical twin" view.
2. **Grafana dashboard (`XLeRobot — Robot State`)** — time-series of end-effector position (x, y, z), joint 0 (shoulder rotation), and rows-per-5-minute count. Sourced live from TimescaleDB. This is the "data twin" view.

**Measure of success in the visualization:**
- The **Omniverse arm reaches** the target ball position within the interpolated motion (visually verifiable — the gripper touches the red ball).
- **Grafana's ee_x/ee_y/ee_z trace** shows a smooth curve arriving at the ball's coordinates (x=40, y=1.75, z=0) at the end of a run.
- **Rows-in-last-5-minute stat** proves data is being persistently written throughout the run.

## 6. Block diagram

See `docs/ARCHITECTURE.md` for the full component diagram with ports and protocols.

Summary flow:

```
user text
   │
   ▼
[nl-command :8010]  ──HTTP──►  [ollama :11434]  (LLM)
   │
   ▼  (TargetPose)
[motion-planner :8020]         (IK + collision check)
   │
   ▼  (joints[6], reachable, collision_free)
[dispatcher :8030]  ──ZMQ PUSH─►  [sim-bridge :5556]  (host / Omniverse)
   │                                    │
   │                                    ▼  (SimState @ 10 Hz)
   │                                [ZMQ PUB :5557]
   │                                    │
   │                                    ▼
   │                              [telemetry]
   │                                ├──SQL──►  [timescaledb :5432]  (history)
   │                                └──RESP─►  [redis :6379]         (latest)
   │                                              │
   ▼                                              ▼
[actuation :8040] ──MQTT──► [mosquitto :1883] ── (physical robot)
                                                  │
[grafana :3000] ◄──SQL─── [timescaledb :5432]     │
                                                  ▼
                                             ee_x, ee_y, ee_z timeseries
                                             joint plots
```

## 7. Protocols and pair-wise contracts

Full route/port/protocol/data-format/initiation/conclusion for every pair of communicating services documented in `contracts/interface-contracts.md`. This document is normative for sprint-2 integration testing.

## 8. Plan of execution

**Sprint 1 (26–30 Jul 2026):** scaffold repo, freeze pydantic v2 contracts, extract each subsystem into its own FastAPI service, per-service unit tests with pass AND fail cases, 10 pair-wise interface contracts documented. **Done — tag `sprint-1`.**

**Sprint 2 (31 Jul 2026):** `docker-compose.yml` wiring all services + infra, integration tests per pair, system test end-to-end, `.github/workflows/ci.yml` (lint + unit + integration + regression), Grafana provisioning, TimescaleDB + Redis persistence proof, horizontal scale demo of stateless `motion-planner`. **In progress — tag `sprint-2` at end.**

See `TASK_ALLOCATION.md` for atomic tasks and per-teammate ownership. See `docs/SPRINT_LOG.md` for what actually shipped each sprint.
