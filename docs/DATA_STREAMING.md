# XLeRobot Digital Twin — Data, Streaming, Aggregation

**Rubric:** Project Data, Streaming, Aggregation (5%) — *"Define digital twin state relevant to your digital twin problem. Demonstrate streaming acquisition of multiple real data streams and its aggregation, conversion to digital twin state."*

---

## 1. Digital twin state — formal definition

At any instant `t`, the digital twin's state `S(t)` is the tuple:

```
S(t) = (
    joints:    [j0, j1, j2, j3, j4, j5]      # 6 float radians
    ee_pose:   (x, y, z)                     # cm, derived via FK
    target:    (x, y, z, r)                  # scene target ball
    obstacles: [ (name, x, y, z, r), ... ]   # scene obstacles
    ts:        wall-clock timestamp
)
```

Pydantic v2 model in `services/shared/schemas.py::SimState`.

**Latest state:** the most recent `S(t)`, held in Redis under key `state:latest` (overwritten every ~100 ms).
**Historical state:** every past `S(t)` since telemetry started, held in TimescaleDB hypertable `robot_state`.

Two storages, two purposes: **Redis for reads that only care about *now*** (dashboards, oncall, "where is the arm right now?"); **TimescaleDB for reads that care about *history*** (Grafana timeseries, regression comparisons, incident forensics).

## 2. Multiple real data streams

Four concurrent streams flow into the digital twin:

| # | Stream | Producer | Transport | Rate | Consumer |
|---|--------|----------|-----------|------|----------|
| 1 | **User commands** | External clients (curl / demo UI) | HTTP `POST /command` | on-demand | `nl-command` |
| 2 | **LLM completions** | Ollama | HTTP JSON | per-command | `nl-command` (parses into `TargetPose`) |
| 3 | **Joint frames** | `dispatcher` (interpolator) | ZMQ PUSH/PULL | 30 fps × ~1 s per command | `sim-bridge` (Omniverse) |
| 4 | **Sim state** | `sim-bridge` extension | ZMQ PUB/SUB | 10 Hz continuous | `telemetry` |

Streams 3 and 4 form the tight simulation loop; stream 1 triggers new motion; stream 2 is the AI intent decode.

All streams are **real** — no mocked inputs in the live system. Tests use containerized real infrastructure (mosquitto, Timescale, Redis) rather than stubs.

## 3. Streaming acquisition mechanics

### 3.1 Command → LLM → planner → dispatcher (HTTP chain, event-driven)

```
POST /command             (external)
  │
  ▼
nl-command  ──►  Ollama :11434     (async httpx)
  │
  ▼
motion-planner /plan               (sync HTTP)
  │
  ▼
dispatcher /dispatch               (sync HTTP)
```

Each hop is an HTTP+JSON request. `services/shared/schemas.py` gives all four services the same pydantic v2 types, so contract violations fail fast with HTTP 422.

### 3.2 Dispatcher → sim-bridge (ZMQ PUSH/PULL, high-frequency)

- Dispatcher binds `PUSH` on `tcp://*:5556`.
- Sim-bridge (Omniverse extension) connects `PULL` on the same address.
- For every dispatched target, dispatcher sends **30 frames of interpolated joint angles** as JSON messages `{"joints": [...], "frame_id": i}`.
- Sim-bridge drains the PULL queue every Kit update tick, applies the newest received joint angles, discards older ones (prevents lag if the sim is slower than dispatch).

### 3.3 Sim-bridge → telemetry (ZMQ PUB/SUB, continuous streaming)

- Sim-bridge binds `PUB` on `tcp://*:5557`.
- Telemetry subscribes from any address (in compose: `tcp://host.docker.internal:5557`).
- At 10 Hz, sim-bridge publishes the full `SimState` snapshot — joints + target + obstacles + implicit ts.
- Publishing is non-blocking (`zmq.NOBLOCK`) so a slow subscriber does not stall the sim tick.

## 4. Aggregation — from raw stream to digital twin state

Two aggregations happen in the `telemetry` service (`services/telemetry/app.py`):

### 4.1 Historical aggregation → TimescaleDB

```python
insert_state(pg_dsn, state)   # → INSERT INTO robot_state (ts, joints, ee_x, ee_y, ee_z) VALUES (...)
```

- One SQL row per received ZMQ message.
- Table is a **TimescaleDB hypertable** (partitioned by `ts`) — cheap time-range queries, automatic partitioning, gigabytes of history without index bloat.
- `robot_state` schema in `infra/timescaledb/init.sql`:
  ```sql
  ts        TIMESTAMPTZ NOT NULL,
  joints    DOUBLE PRECISION[] NOT NULL,   -- 6-element array
  ee_x, ee_y, ee_z  DOUBLE PRECISION       -- flattened for cheap Grafana queries
  ```

### 4.2 Latest-state aggregation → Redis

```python
set_latest_state(redis_url, state)   # → SET state:latest <json(state)>
```

- One key (`state:latest`), overwritten every tick. Old values discarded.
- Serialization: JSON via `SimState.model_dump_json()`.
- Any client wanting "where is the arm *now*?" reads this one key — O(1), no time-range query needed.

Both writes are wrapped in a `try/except` that logs and continues, so a transient DB or Redis error does not kill the telemetry loop.

## 5. Conversion to digital twin state — end-to-end proof

```
Omniverse arm moves (real sim, real physics)
  → sim-bridge publishes SimState @ 10 Hz  (stream)
  → telemetry SUBs and decodes into pydantic SimState  (raw → typed)
  → 2 aggregations:
       ├── row per tick   → TimescaleDB  (historical state)
       └── overwrite key  → Redis        (latest state)
  → Grafana queries TimescaleDB → visualizes state over time
  → Any client reads Redis → knows current state instantly
```

## 6. Tests proving the streams work

| Test | What it proves |
|----|----|
| `tests/integration/test_sim_to_telemetry.py` (Raziq-07) | Publishing a fake `SimState` via real Timescale + Redis containers lands a matching row AND updates Redis latest key |
| `tests/integration/test_actuation_mqtt.py` (Ibrohim-07) | Real MQTT round-trip against real mosquitto container — proves the outbound-to-physical-robot stream works |
| `tests/system/test_end_to_end.py` (A-07) | Full stack: `POST /command` → within 10 s → new row appears in `robot_state` with plausible joints |

## 7. Persistence proof (data + state, both halves of the rubric)

See `docs/PERSISTENCE_PROOF.md` (Raziq-09). Procedure: run pipeline → screenshot Timescale row count + Redis latest → `docker compose restart timescaledb redis` → screenshot again → **both values identical after restart** because of named volumes on both stores. Historical data + latest state both persistent.
