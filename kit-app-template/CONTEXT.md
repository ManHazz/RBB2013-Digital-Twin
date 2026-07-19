# Xlerobot Digital Twin — Project Context

## What this project is
An NVIDIA Omniverse digital twin of a 6-DOF robot arm. The arm is rendered in
Omniverse Kit and controlled in real time via ZMQ messages. The long-term goal
is to make it LLM-driven: type "grab the ball" and the robot moves and grabs it.

## Stack
- NVIDIA Omniverse Kit 110.x (kit-app-template)
- Python extension inside Omniverse (USD + ZMQ)
- External Python scripts send commands over ZMQ
- Future: MQTT bridge, IK solver (ikpy), Claude API as brain

---

## Folder structure

```
source/
├── apps/
│   └── digitaltwin.xlerobot.kit        # App entry point — what ./repo.sh launch reads
└── extensions/
    └── digitaltwin.xlerobot_extension/
        ├── config/
        │   └── extension.toml          # Extension metadata, declares python module name
        └── digitaltwin/
            └── xlerobot_extension/
                ├── extension.py        # ALL the logic (see below)
                └── __init__.py
```

Also in the project root (alongside kit-app-template):
- `xlerobot_control.py` — sends joint angle commands over ZMQ
- `spiral_sender.py`    — sends a spiral motion pattern over ZMQ

---

## extension.py — what it does

This is the entire brain of the Omniverse side.

### 1. Robot geometry constants (top of file, edit freely)
All lengths in centimetres, Y-up convention (Omniverse default).
```python
BALL_RADIUS_BASE = 4.0   # J0 base joint sphere
LINK_1_LENGTH    = 30.0  # upper arm  J1→J2
LINK_2_LENGTH    = 25.0  # forearm    J2→J3
LINK_3_LENGTH    = 15.0  # wrist      J3→J4
LINK_4_LENGTH    = 8.0   # palm       J4→J5
GRIPPER_LENGTH   = 6.0   # each finger
ZMQ_PORT         = 5556  # PULL socket port
```

### 2. USD scene build (runs once on startup)
Builds the arm from USD primitives:
- `UsdGeom.Sphere`   → joint balls
- `UsdGeom.Cylinder` → link sticks
- `UsdShade.Material` → colours (steel blue joints, grey links, amber gripper)

Hierarchy is nested: J1 is child of J0, J2 child of J1, etc.
Rotating J0 rotates the whole arm — same as a real robot.

### 3. Joint axis mapping
| Joint | Part          | Rotation axis |
|-------|---------------|---------------|
| j0    | Base yaw      | Y             |
| j1    | Shoulder pitch| Z             |
| j2    | Elbow pitch   | Z             |
| j3    | Wrist pitch   | Z             |
| j4    | Wrist roll    | X             |
| j5    | Gripper       | Z (±spread)   |

All angles in **radians**. Send only the keys you want to update.

### 4. ZMQ PULL socket
Bound on `tcp://0.0.0.0:5556` at startup.
Non-blocking receive (RCVTIMEO=0) — never waits, just checks each frame.

### 5. Per-frame update loop
Hooked into Omniverse's update event stream (~60fps).
Each frame:
- Drains the ZMQ queue, keeps only the **latest** message (discards stale)
- Updates stored joint angles for any keys present
- Calls `apply_joint_angles()` to move the robot

### 6. Message format
```json
{"j0": 0.0, "j1": 0.5, "j2": -0.3, "j3": 0.1, "j4": 0.0, "j5": 0.4}
```
Send over ZMQ PUSH → port 5556.
Only include joints you want to change — others hold last position.

---

## How to run

```bash
cd kit-app-template
./repo.sh launch          # starts Omniverse with the robot loaded

# in another terminal
python xlerobot_control.py   # or spiral_sender.py
```

---

## Roadmap: LLM-driven "grab the ball"

### Phase 1 — Add a ball to the scene
Edit `extension.py` to spawn a `UsdGeom.Sphere` at a fixed known position on startup.
Use the same `_add_ball()` / `_translate()` helpers already in the file.
Target position: something reachable, e.g. x=20, y=5, z=0 cm.

### Phase 2 — Pose library
Create a `poses.py` file with named waypoints:
```python
POSES = {
    "home":     {"j0":0.0, "j1":0.0, "j2":0.0,  "j3":0.0, "j4":0.0, "j5":0.3},
    "approach": {"j0":0.0, "j1":0.8, "j2":-0.6, "j3":0.2, "j4":0.0, "j5":0.3},
    "grab":     {"j0":0.0, "j1":0.9, "j2":-0.7, "j3":0.3, "j4":0.0, "j5":0.0},
    "lift":     {"j0":0.0, "j1":0.6, "j2":-0.4, "j3":0.2, "j4":0.0, "j5":0.0},
}
```
Tune by watching the robot in Omniverse.
A motion = a list of pose names sent over ZMQ with `time.sleep()` between them.

### Phase 3 — LLM command interpreter
`llm_controller.py` — takes a text prompt, calls Claude API, gets back a pose sequence:

System prompt to Claude:
```
You control a 6-DOF robot arm digital twin.
Ball is at position (x=20, y=5, z=0) cm.
Available poses: home, approach, grab, lift.
Reply ONLY with a JSON array:
[{"pose":"home","wait":1.0},{"pose":"approach","wait":1.5},{"pose":"grab","wait":1.0}]
```

User says "grab the ball" → Claude returns the sequence → script sends it over ZMQ.

Claude API model string: `claude-sonnet-4-6`

### Phase 4 — Inverse kinematics (dynamic ball positions)
Use `ikpy` to compute joint angles from a 3D target position:
```bash
pip install ikpy
```
Define the arm chain from the link lengths in `extension.py`.
LLM says "move to X,Y,Z then close gripper" → IK computes j0–j5.
Ball position can be read directly from the USD stage.

### Phase 5 — State feedback
Add a ZMQ PUSH socket on the Omniverse side to publish robot state
(end effector position, gripper state) back to the external script.
LLM subscribes and makes decisions based on actual robot state.

---

## MQTT integration (in progress)
Bridge: `mqtt_zmq_bridge.py`
```
MQTT broker → subscribe to "xlerobot/joints" → forward JSON → ZMQ port 5556
```
Payload format is identical to the ZMQ message format above.

---

## Key file: extension.toml
Located at:
`source/extensions/digitaltwin.xlerobot_extension/config/extension.toml`

Must have:
```toml
[[python.module]]
name = "digitaltwin.xlerobot_extension"

[python.pip]
packages = ["pyzmq"]
```

pyzmq must be installed into the **packman bundled Python**, not system Python:
```bash
find ~/.cache/packman -name "python3" -path "*/bin/python3" | head -1
# use that path to pip install pyzmq
```

---

## Environment
- Machine: manhazz-arch (EndeavourOS / Arch Linux)
- GPU: RTX 4050 Max-Q (6GB VRAM)
- Kit SDK: 110.x
- Project path: ~/Documents/digitaltwin/nvidia-omniverse/ (or /media/RBB2013/directory/kit-app-template on lab PCs)
