# Interface Contracts

For every pair of communicating services: route/topic, port, protocol, data format, when initiated, when concluded.

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

- **Route:** `POST /command`
- **Port:** 8010
- **Protocol:** HTTP/JSON
- **Payload example:**
  ```json
  // request
  { "text": "pick up the ball" }
  // response (200)
  { "x": 40.0, "y": 13.75, "z": 0.0 }
  ```
- **Initiated:** user submits a text instruction.
- **Concluded:** a `TargetPose` is returned to the caller.
- **Error modes:**
  - `422` — empty text, the LLM's plan could not be parsed as JSON, or the plan resolved to only "home" steps (no movement target).
  - `502` — Ollama unreachable or returned an HTTP error.

## nl-command → ollama

- **Route:** `POST /api/generate`
- **Port:** 11434
- **Protocol:** HTTP/JSON
- **Payload example:**
  ```json
  // request
  {
    "model": "qwen2.5:3b",
    "prompt": "/no_think\nCommand: pick up the ball",
    "system": "<SYSTEM_PROMPT — see app.py>",
    "stream": false
  }
  // response
  { "response": "[{\"action\":\"above\",\"wait\":1.0},{\"action\":\"grab\",\"wait\":1.0}]" }
  ```
- **Initiated:** on every `/command` call, after validating the input text is non-empty.
- **Concluded:** Ollama returns a completion string containing a JSON array of action steps, which nl-command parses and converts to an `(x, y, z)` target via `action_target()`.
- **Note:** nl-command has no live scene socket (unlike the original `llm_controller.py`), so it resolves targets against a fixed `FALLBACK_TARGET` rather than live obstacle/ball positions.
- **Error modes:** connection/timeout to Ollama surfaces as `502` back to the client.

## nl-command → motion-planner

- **Route:** `POST /plan`
- **Port:** 8020
- **Protocol:** HTTP/JSON
- **Payload example:**
  ```json
  // request
  { "target": { "x": 40.0, "y": 13.75, "z": 0.0 } }
  // response
  { "joints": [0,0,0,0,0,0], "reachable": true, "collision_free": true }
  ```
- **Initiated:** once nl-command has successfully resolved a `TargetPose`.
- **Concluded:** motion-planner returns a `PlanResponse`.
- **Error modes:** owned by motion-planner (Ariq's contract rows) — e.g. `reachable: false` for out-of-range targets.

---
<!-- Remaining sections owned by other teammates — fill in your own rows here:
## motion-planner → dispatcher   (Ariq)
## dispatcher → sim-bridge       (Ibrohim)
## actuation → mosquitto         (Ibrohim)
## sim-bridge → telemetry        (Raziq)
## telemetry → timescaledb       (Raziq)
## telemetry → redis             (Raziq)
-->