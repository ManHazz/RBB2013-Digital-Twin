# XLeRobot Digital Twin — Architecture

This document describes the physical topology, service responsibilities, and communication patterns of the XLeRobot Digital Twin. It complements `docs/SPECIFICATION.md` (problem/purpose) and `contracts/interface-contracts.md` (per-pair contract details).

---

## 1. Component diagram

```
                                     ┌────────────────────────────────────┐
                                     │  HOST (Omniverse Kit — GPU-bound)  │
                                     │                                    │
                                     │   ┌──────────────────────────────┐ │
                     ZMQ PUSH        │   │   sim-bridge (extension)     │ │
                     tcp://*:5556 ───┼──►│  digitaltwin.xlerobot_       │ │
                          ▲          │   │      extension               │ │
                          │          │   │  - PULL joint frames         │ │
                          │          │   │  - apply to USD arm          │ │
                          │          │   │  - PUB SimState @ 10 Hz      │ │
                          │          │   └──────────────┬───────────────┘ │
                          │          │                  │ ZMQ PUB         │
                          │          │                  │ tcp://*:5557    │
                          │          └──────────────────┼─────────────────┘
                          │                             │
                          │                             │
   ┌──────────────────────┴──────────────────────────┐  │
   │   DOCKER COMPOSE NETWORK  (infra/docker-       │  │
   │   compose.yml — one machine, all containers)   │  │
   │                                                 │  │
   │  ┌───────────┐   ┌──────────┐   ┌─────────────┐│  │
   │  │nl-command │──►│ planner  │──►│ dispatcher  ││──┘
   │  │  :8010    │HTTP│  -lb     │HTTP│  :8030     ││
   │  └─────┬─────┘   │ (nginx)  │   │             ││
   │        │HTTP     │  :8020   │   └─────┬───────┘│
   │  ┌─────▼─────┐   └────┬─────┘         │HTTP    │
   │  │  ollama   │        │(round-robin)  ▼        │
   │  │  :11434   │        │        ┌───────────┐   │
   │  │ (on host) │        ▼        │ actuation │   │
   │  └───────────┘   ┌─────────┐   │  :8040    │   │
   │                  │ motion  │   └─────┬─────┘   │
   │                  │-planner │         │MQTT     │
   │                  │ ×N      │         ▼         │
   │                  └─────────┘   ┌───────────┐   │
   │                                │ mosquitto │──►│ physical robot
   │                                │  :1883    │   │  (xlerobot/cmd)
   │                                └───────────┘   │
   │                                                 │
   │           ┌──────────────────────────────────┐  │
   │           │           telemetry              │  │
   │           │  SUB ZMQ 5557 → decode SimState  │  │
   │           └────┬────────────────────┬────────┘  │
   │                │SQL                 │RESP       │
   │                ▼                    ▼           │
   │        ┌──────────────┐    ┌──────────────┐    │
   │        │ timescaledb  │    │    redis     │    │
   │        │   :5432      │    │   :6379      │    │
   │        │ (history)    │    │  (latest)    │    │
   │        └──────┬───────┘    └──────────────┘    │
   │               │SQL                              │
   │               ▼                                 │
   │        ┌──────────────┐                         │
   │        │   grafana    │                         │
   │        │   :3000      │                         │
   │        │ (dashboards) │                         │
   │        └──────────────┘                         │
   └─────────────────────────────────────────────────┘
```

## 2. Service catalogue

| Service | Was | Container | Port(s) | Language / framework | Responsibility |
|---------|-----|-----------|---------|----------------------|----------------|
| `nl-command` | `llm_controller.py` | ✅ | 8010 | Python / FastAPI | Take user text, call Ollama, return `TargetPose` |
| `motion-planner` | `robot_ik.py` | ✅ | 8020 (internal) | Python / FastAPI | IK solve + reachability + collision check |
| `planner-lb` | new | ✅ | 8020 (public) | nginx | Round-robin `motion-planner` replicas for horizontal scale |
| `dispatcher` | interpolator logic | ✅ | 8030, 5556 | Python / FastAPI + pyzmq | 30 fps interpolation, ZMQ PUSH frames to sim, HTTP-trigger actuation |
| `sim-bridge` | `extension.py` | ❌ (host, GPU) | 5556 PULL, 5557 PUB | Python / Omniverse Kit | Apply joints in USD scene, publish live `SimState` |
| `actuation` | MQTT publisher | ✅ | 8040 | Python / FastAPI + paho-mqtt | On dispatcher's HTTP trigger, publish `xlerobot/cmd` |
| `telemetry` | new | ✅ | daemon | Python / pyzmq + psycopg + redis | SUB sim state → write TimescaleDB row + Redis latest |
| `ollama` | infra | 🟡 host | 11434 | LLM runtime | LLM inference |
| `timescaledb` | infra | ✅ | 5432 | TimescaleDB 2.x on Postgres 15 | Time-series persistence |
| `redis` | infra | ✅ | 6379 | Redis 7 (AOF+RDB) | Latest-state cache |
| `mosquitto` | infra | ✅ | 1883 | Eclipse Mosquitto 2 | MQTT broker |
| `grafana` | infra | ✅ | 3000 | Grafana 10.4 | Time-series visualization |

## 3. Deployment boundary — why sim-bridge is on the host

`sim-bridge` is the Omniverse Kit extension `digitaltwin.xlerobot_extension`. It must run **on the host** because Omniverse Kit needs:
- GPU-accelerated Vulkan for RTX rendering.
- Direct X server access (windowed viewport).
- Kit's own bundled Python runtime and USD stack (not a slim Python container).

Containerizing it would require GPU passthrough + X11 forwarding for negligible benefit and significant fragility. Instead, the boundary is **explicit**: sim-bridge lives on the host and talks to the compose network via `host.docker.internal:5556/5557`. All other services are containerized.

This is a deliberate architectural decision, not a gap — documented up front in `PLAN.md §0`.

## 4. Communication patterns

### 4.1 Request–response (HTTP + JSON)
Used for user-triggered command chains: `nl-command → ollama`, `nl-command → motion-planner`, `motion-planner → dispatcher`, `dispatcher → actuation`. Synchronous, low frequency, needs status codes.

### 4.2 Push–pull (ZMQ PUSH/PULL)
Used for high-frequency frame streaming: `dispatcher → sim-bridge`. Fire-and-forget, no ack. Round-robin at receiver naturally, though we run one sim-bridge instance.

### 4.3 Publish–subscribe (ZMQ PUB/SUB)
Used for continuous state broadcasting: `sim-bridge → telemetry`. Sim publishes even if nobody subscribes; late subscribers only see messages after their connect. Fan-out — multiple subscribers could be added (a monitoring UI, a recorder) without touching the publisher.

### 4.4 Message queue (MQTT)
Used for outbound command to the physical robot: `actuation → mosquitto → <physical robot>`. Broker-based; the robot subscribes to `xlerobot/cmd`. Decouples us from the robot's uptime.

### 4.5 SQL and RESP
`telemetry → timescaledb` (INSERT), `telemetry → redis` (SET), `grafana → timescaledb` (SELECT). Standard.

## 5. Contract types (single source of truth)

All pydantic v2 models in `services/shared/schemas.py`. Version 1.0, frozen in sprint 1. Only the tech lead (Aiman) edits this file — otherwise every service could disagree on a field and the whole chain breaks silently.

Key types:
- `CommandRequest`, `TargetPose`, `PlanRequest`, `PlanResponse`
- `DispatchRequest`, `DispatchResponse`
- `SimState` (with nested `TargetPose` for ee_pose)
- `ActuationCommand`

Every service imports from this module — the same types are the contract at every hop.

## 6. Scaling and persistence design decisions

### Horizontal scale — `motion-planner`
- IK is pure math, no per-request state. Multiple replicas are safe.
- `planner-lb` (nginx) fronts them via Docker's DNS-based service discovery — `motion-planner:8020` resolves to all replica IPs, nginx round-robins.
- Demoed with `docker compose up --scale motion-planner=3` and a burst test — see `docs/SCALING_PROOF.md`.

### Vertical scale — `dispatcher`
- Holds ZMQ socket state (connected sim-bridge). Cannot trivially replicate.
- Not a bottleneck at 30 fps.

### Persistence — TimescaleDB
- Named volume `timescaledb-data` on `/var/lib/postgresql/data`.
- Data survives `docker compose restart` and `docker compose down` (not `down -v`).
- Hypertable on `robot_state(ts, ...)` for cheap time-range queries as history grows.

### Persistence — Redis
- Named volume `redis-data` on `/data`.
- `--appendonly yes --save 60 1` — AOF for durability + periodic RDB snapshots.
- `state:latest` survives restart.

Both proven in `docs/PERSISTENCE_PROOF.md`.

## 7. Test topology

```
tests/
├── unit/         — per-service pure logic, no infra, fast
├── integration/  — service pairs against REAL infra (testcontainers spins Timescale, Redis, mosquitto)
├── system/       — full stack via docker compose, end-to-end assertion (command → row in Timescale)
└── regression/   — golden IK cases, run on every CI push, fails if math drifts
```

CI in `.github/workflows/ci.yml` (Bento-07): `lint → unit → integration → regression`. Every push. See rubric coverage in `docs/SPECIFICATION.md §8`.
