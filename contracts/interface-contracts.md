# Interface Contracts

Source of truth for every pair of communicating services in the XLeRobot Digital Twin. Rows below map 1:1 to PLAN.md Phase B. Each row has a dedicated section under the table — teammates own filling in their own rows (payload examples, edge cases, error modes).

**Do not edit rows you do not own.** See `TASK_ALLOCATION.md` for ownership.

## Summary table

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

---

## client → nl-command

**Owner:** Bento

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## nl-command → ollama

**Owner:** Bento

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## nl-command → motion-planner

**Owner:** Bento (input side) / Ariq (output side)

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## motion-planner → dispatcher

**Owner:** Ariq (input side) / Ibrohim (output side)

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## dispatcher → sim-bridge

**Owner:** Ibrohim

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## sim-bridge → telemetry

**Owner:** Raziq

**Payload example:**
```json
{
  "joints": [0.12, -0.45, 1.02, 0.00, 0.33, -0.10],
  "ee_pose": {"x": 0.42, "y": 0.15, "z": 0.30},
  "ts": 1721990400.123
}
```

**Initiated:** sim-bridge publishes one `SimState` message on every simulation tick (each frame applied in Omniverse), via ZMQ PUB on port 5557.

**Concluded:** telemetry's SUB socket receives the message and validates it against the `SimState` schema; the exchange concludes once `insert_state()` and `set_latest_state()` have both run for that message. This is a fire-and-forget publish — no ack is sent back to sim-bridge.

**Error modes:**
- Malformed/incomplete payload → `SimState.model_validate` raises a validation error → caught by telemetry's outer try/except, logged, message dropped (no retry).
- ZMQ PUB/SUB has no delivery guarantee: if telemetry connects after sim-bridge starts publishing, frames sent before the subscription completes are lost.
- If the telemetry container is down entirely, all sim state during that window is lost — no buffering or replay.

---

## telemetry → timescaledb

**Owner:** Raziq

**Payload example:**
```sql
INSERT INTO robot_state (ts, joints, ee_x, ee_y, ee_z)
VALUES (
  to_timestamp(1721990400.123),
  ARRAY[0.12, -0.45, 1.02, 0.00, 0.33, -0.10],
  0.42, 0.15, 0.30
);
```

**Initiated:** on every `SimState` message telemetry receives from sim-bridge — one INSERT per message via `insert_state()`.

**Concluded:** the transaction commits (`conn.commit()`); the row is durable in the `robot_state` hypertable.

**Error modes:**
- DB connection dropped or Timescale unavailable → psycopg raises a connection error → caught by telemetry's outer try/except, logged, loop continues (that state reading is dropped — no retry queue).
- Malformed data (wrong joint-array length, missing field) never reaches this insert — it's rejected earlier by `SimState` schema validation.

---

## telemetry → redis

**Owner:** Raziq

**Payload example:**
key: state:latest
value: {"joints": [0.12,-0.45,1.02,0.00,0.33,-0.10], "ee_pose": {"x":0.42,"y":0.15,"z":0.30}, "ts":1721990400.123}

**Initiated:** on every `SimState` message telemetry receives — same trigger as the TimescaleDB insert, via `set_latest_state()`.

**Concluded:** the `SET` completes and overwrites whatever was previously at `state:latest` — this is the piece that proves *state* persistence (only the most recent reading is kept, no history, unlike the TimescaleDB side).

**Error modes:**
- Redis unavailable → connection error raised → caught by telemetry's outer try/except, logged, loop continues; the latest-state cache simply goes stale until Redis recovers (no retry/backoff implemented).

---

## actuation → mosquitto

**Owner:** Ibrohim

**Payload example:**
```json
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## grafana → timescaledb

**Owner:** Raziqw

**Payload example:**
```sql
SELECT ts, joints, ee_x, ee_y, ee_z
FROM robot_state
WHERE ts > now() - interval '1 hour'
ORDER BY ts;
```

**Initiated:** on each Grafana dashboard panel refresh (Grafana's own configured polling interval — a read-only query, no side effects on the service).

**Concluded:** query returns the matching rows and the panel renders them.

**Error modes:**
- TimescaleDB unreachable → Grafana panel shows a query error / "no data", no retries triggered from the telemetry side (this is a pure read path, telemetry itself isn't involved once the row is committed).
- Wide time-range queries over raw `robot_state` rows can get slow without a continuous aggregate — not addressed in this scope; documented here as a known limitation rather than solved.