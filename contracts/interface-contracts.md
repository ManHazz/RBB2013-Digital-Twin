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
Request: {"target": {"x": 35.0, "y": 5.0, "z": 10.0}}
Response: {"joints": [0.32, 1.54, -1.47, 3.08, 0.0, 0.0], "reachable": true, "collision_free": true}
```

**Initiated:** nl-command has resolved a pose from the LLM and forwards it to motion-planner

**Concluded:** motion-planner returns the plan, including reachable=false or collision_free=false for invalid targets

**Error modes:** target out of arm's reach returns reachable=false (HTTP 200, not an error); target causes self-collision returns collision_free=false (HTTP 200, not an error)

---

## motion-planner → dispatcher

**Owner:** Ariq (input side) / Ibrohim (output side)

**Payload example:**
```json
Request: {"joints": [0.32, 1.54, -1.47, 3.08, 0.0, 0.0]}
Response: {"accepted": true}
```

**Initiated:** motion-planner has produced a valid plan (reachable=true, collision_free=true) and forwards joints to dispatcher

**Concluded:** dispatcher acknowledges receipt with accepted=true

**Error modes:** motion-planner does not call dispatcher if reachable=false or collision_free=false — invalid plans stop here and are never forwarded

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
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## telemetry → timescaledb

**Owner:** Raziq

**Payload example:**
```sql
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

---

## telemetry → redis

**Owner:** Raziq

**Payload example:**
```
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_

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

**Owner:** Raziq

**Payload example:**
```sql
```

**Initiated:** _tbd_

**Concluded:** _tbd_

**Error modes:** _tbd_
