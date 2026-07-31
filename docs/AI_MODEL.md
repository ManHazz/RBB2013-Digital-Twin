# XLeRobot Digital Twin — AI / Algorithmic / Behavioral Model

**Rubric:** Project AI or Algorithmic/Behavioral Model (5%) — *"Demonstrate any AI or Behavioral model relevant to your digital twin. Show it is responsive to data ingested and updates digital twin state or any action."*

The digital twin uses **two coupled models**: a Large Language Model for intent recognition, and a classical inverse-kinematics + collision solver for motion generation. Both are wrapped behind FastAPI HTTP services, so their inputs are ingested from real data streams and their outputs update the digital twin's state.

---

## Model 1 — LLM-based intent parser (`nl-command` service)

**Purpose:** Convert a free-form natural-language command into a structured target pose the rest of the pipeline can act on.

**Model:** Qwen2.5 3B parameters, served locally via Ollama (`http://host:11434/api/generate`). Configurable via env var `OLLAMA_MODEL`.

**Data ingested:**
- User command string (from `POST /command`).
- System prompt describing valid arm actions and required output schema.
- Fallback target pose (used when the LLM emits only a "home" step).

**Behavior — how it responds to input:**

1. Text arrives at `POST /command` on port 8010.
2. `nl-command` forwards a prompt+system to Ollama. The system prompt constrains the LLM to output only a JSON array of high-level action steps: `[{"action": "above|grab|lift|place|home", "wait": <seconds>}]`.
3. `nl-command` parses the LLM's raw completion, repairs malformed JSON (unquoted keys, `<think>` blocks) via `repair_json()`.
4. `nl-command` maps each action to an `(x, y, z)` target using `action_target()`:
   - `above` → target position with `y += 12 cm` (approach from above the ball).
   - `grab` → target position at the ball.
   - `lift` → target position with `y += 25 cm` (lift the ball).
   - `place` → target position (release).
5. Returns a `TargetPose(x, y, z)` — the digital twin's next commanded end-effector goal.

**How it updates digital twin state:**
- The returned `TargetPose` feeds into `motion-planner` → `dispatcher` → sim-bridge, where it becomes the new set of joint angles that update the arm in Omniverse **and** stream into TimescaleDB + Redis.

**Failure modes exercised in tests:**
- Empty text → HTTP 422 (`tests/unit/test_nl_command.py::test_empty_text_returns_422`).
- Garbled LLM response → HTTP 422 (`tests/unit/test_nl_command.py::test_garbled_ollama_returns_422`).
- Ollama unreachable → HTTP 502.

---

## Model 2 — Inverse kinematics + collision checker (`motion-planner` service, `robot_ik.py`)

**Purpose:** Given a target end-effector pose, compute 6 joint angles that reach the pose without self-collision or obstacle collision.

**Model type:** Classical analytical/numerical IK with a spherical-approximation collision checker over arm segments and known obstacles. Public API in `services/motion_planner/robot_ik.py`:

- `forward_kinematics(joints) -> Point3D` — where the gripper ends up given joint angles.
- `gripper_tip(joints) -> Point3D` — end-effector position specifically.
- `solve(target) -> joints` — inverse: find joint angles that reach `target`.
- `reachable(target) -> bool` — target is within the arm's workspace.
- `accuracy_at(joints, target) -> float` — Euclidean distance between FK(joints) and target.
- `arm_points(joints) -> list` — spherical waypoints along the arm for collision checks.
- `collides(joints, obstacles) -> bool` — any arm sphere overlaps any obstacle sphere?

**Data ingested:**
- `PlanRequest.target` — an `(x, y, z)` pose. Comes from `nl-command`'s LLM output, so ultimately from a user command.
- (Internal) hard-coded obstacle list from the scene.

**Behavior — how it responds to input:**

1. `POST /plan` receives `{"target": {"x", "y", "z"}}`.
2. Calls `reachable(target)`. If false → returns `{joints: [0]*6, reachable: false, collision_free: true}` (HTTP 200, negative answer — not an error).
3. Calls `solve(target)` to get joint angles.
4. Calls `collides(joints, obstacles)`. If true → returns `{joints, reachable: true, collision_free: false}`.
5. Otherwise → returns `{joints, reachable: true, collision_free: true}`.

**How it updates digital twin state:**
- Returned joint angles are passed to `dispatcher`, which interpolates from current pose to the target over 30 frames at 30 fps, then ZMQ-pushes each frame to sim-bridge. Sim-bridge applies the angles → the digital twin arm moves in Omniverse → the sim tick publishes a new `SimState` → telemetry writes it to TimescaleDB + Redis. State updated end-to-end.

**Failure modes exercised in tests (rubric requires pass AND fail cases):**
- Reachable target → correct joints returned, forward-kinematics round-trip within 1e-3 (`tests/unit/test_motion_planner.py::test_ik_roundtrip`).
- Unreachable target → `reachable=False` returned, no crash (`test_unreachable_target_rejected`).
- Colliding target → `collision_free=False` returned (`test_colliding_target_rejected`).
- Golden regression suite in CI: fixed target→(reachable, collision_free) pairs, IK output drift fails the build (`tests/regression/test_golden_ik.py`).

---

## Why both models are needed

| Model | Role | Ingested data | Updates state |
|-------|------|---------------|---------------|
| LLM (Qwen2.5 via Ollama) | Semantic — "what does the user want?" | User text | Produces `TargetPose` |
| IK + collision | Physical — "how do we get there safely?" | `TargetPose` | Produces joint angles that become the sim's new joint state |

Neither is sufficient alone: an LLM can't do 6-DoF IK reliably; a solver can't understand English. Chained, they turn a sentence into a validated, collision-free trajectory that updates the digital twin.

## Live demo

To see both models responding to real input:

```bash
# 1. Start Ollama on host, ensure qwen2.5:3b is pulled
ollama pull qwen2.5:3b
ollama serve

# 2. Bring up compose stack
docker compose -f infra/docker-compose.yml up -d

# 3. Ensure Omniverse Kit is running with digitaltwin.xlerobot_extension enabled
#    (see kit-app-template/source/apps/digitaltwin.xlerobot.kit)

# 4. Send a command
curl -X POST http://localhost:8010/command \
     -H 'content-type: application/json' \
     -d '{"text": "pick up the ball"}'
# → returns {"x": 40.0, "y": 13.75, "z": 0.0}  (approach position)

# 5. Watch Omniverse — arm animates to that position via IK + interpolation
# 6. Watch Grafana at http://localhost:3000 — ee_x/ee_y/ee_z traces update live
```
