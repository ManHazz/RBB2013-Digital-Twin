# =============================================================================
# llm_controller.py
# Natural-language control of the xlerobot digital twin.
#
#   command --> Ollama (LLM) --> pose plan
#           --> IK (robot_ik) --> joint angles
#           --> collision check vs live obstacles
#               - if a waypoint collides, try alternative approach angles
#               - if none work, stop and report
#           --> smooth 30 fps interpolation --> ZMQ --> Omniverse
#
# Scene awareness: reads target + obstacle positions live from the extension's
# state socket (port 5557), with a hardcoded fallback if the socket is silent.
# =============================================================================
import zmq
import json
import time
import math
import re
import requests

import robot_ik as ik

# --- connection config ---
ZMQ_PORT_CMD   = 5556
ZMQ_PORT_STATE = 5557
OLLAMA_URL     = "http://localhost:11434/api/generate"
OLLAMA_MODEL   = "qwen2.5:3b"

# --- fallback scene (used only if the state socket is silent) ---
FALLBACK_TARGET = {"x": 40.0, "y": 1.75, "z": 0.0, "r": 1.75}
FALLBACK_OBSTACLES = [
    {"name": "obstacle_A", "x": 25.0, "y": 12.0, "z": 8.0,  "r": 4.0},
    {"name": "obstacle_B", "x": 30.0, "y": 20.0, "z": -10.0, "r": 5.0},
]

HOME = {"j0": 0.0, "j1": 0.0, "j2": 0.0, "j3": 0.0, "j4": 0.0, "j5": 0.3}
GRIP_OPEN, GRIP_CLOSED = 0.3, 0.0


# =============================================================================
# SCENE STATE  (live from Omniverse, with fallback)
# =============================================================================
class SceneState:
    def __init__(self, ctx):
        self.sock = ctx.socket(zmq.SUB)
        self.sock.connect(f"tcp://localhost:{ZMQ_PORT_STATE}")
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.setsockopt(zmq.RCVTIMEO, 0)
        self.target    = dict(FALLBACK_TARGET)
        self.obstacles = [dict(o) for o in FALLBACK_OBSTACLES]
        self.live = False

    def refresh(self):
        """Pull the most recent state message if any are queued."""
        latest = None
        try:
            while True:
                latest = self.sock.recv_json(flags=zmq.NOBLOCK)
        except zmq.Again:
            pass
        if latest:
            self.target    = latest.get("target", self.target)
            self.obstacles = latest.get("obstacles", self.obstacles)
            self.live = True
        return self.live


# =============================================================================
# LLM  (decides the high-level plan; IK does the geometry)
# =============================================================================
SYSTEM_PROMPT = """You control a robot arm that can pick up a ball, avoiding obstacles.
Reply ONLY with a JSON array of action steps. Each step has "action" and "wait" (seconds).
Valid actions:
  "home"  - return to rest position
  "above" - move above the target ball (gripper open)
  "grab"  - lower onto the ball and close gripper
  "lift"  - raise the ball up high
  "place" - lower and release the ball
Use 3-5 steps. Example for "pick up the ball":
[
  {"action": "home",  "wait": 0.8},
  {"action": "above", "wait": 1.0},
  {"action": "grab",  "wait": 1.0},
  {"action": "lift",  "wait": 1.0}
]
If unsure, return a home step. Never output joint angles, only the actions above."""


def repair_json(raw: str) -> str:
    if "<think>" in raw:
        raw = raw[raw.rfind("</think>") + 8:].strip()
    raw = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', raw)
    return raw


def ask_llm(command: str) -> list:
    resp = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": f"/no_think\nCommand: {command}",
        "system": SYSTEM_PROMPT,
        "stream": False,
    }, timeout=60)
    raw = repair_json(resp.json()["response"].strip())
    print(f"[LLM] {raw}")

    start, end = raw.find("["), raw.rfind("]") + 1
    parsed = json.loads(raw[start:end]) if start != -1 else json.loads(raw)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not parsed:
        raise ValueError("empty plan")
    return parsed


# =============================================================================
# PLANNING  (actions -> target xyz -> IK angles, with collision re-planning)
# =============================================================================
def action_target(action: str, scene: SceneState):
    """Map an action to a target (x,y,z) and gripper state."""
    t = scene.target
    if action == "home":
        return None, GRIP_OPEN                       # special: literal home pose
    if action == "above":
        return (t["x"], t["y"] + 12.0, t["z"]), GRIP_OPEN
    if action == "grab":
        return (t["x"], t["y"], t["z"]), GRIP_CLOSED
    if action == "lift":
        return (t["x"], t["y"] + 25.0, t["z"]), GRIP_CLOSED
    if action == "place":
        return (t["x"], t["y"], t["z"]), GRIP_OPEN
    return None, GRIP_OPEN


def plan_angles(action: str, scene: SceneState):
    """
    Resolve an action to joint angles. If the direct solution collides with an
    obstacle, try alternative approach angles (yaw offsets). Returns
    (angles or None, status_string).
    """
    tgt, grip = action_target(action, scene)

    if tgt is None:  # home
        a = dict(HOME); a["j5"] = grip
        return a, "ok"

    x, y, z = tgt
    if not ik.reachable(x, y, z):
        return None, f"target {action} out of reach"

    # primary solution
    angles = ik.solve(x, y, z)
    angles["j5"] = grip
    if not ik.collides(angles, scene.obstacles):
        return angles, "ok"

    # ---- collision: try alternative approaches ----
    # 1) approach the target from small yaw offsets (swing around obstacles)
    base_yaw = math.atan2(z, x)
    horiz = math.sqrt(x * x + z * z)
    for dyaw_deg in (15, -15, 30, -30, 45, -45):
        dyaw = math.radians(dyaw_deg)
        nx = horiz * math.cos(base_yaw + dyaw)
        nz = horiz * math.sin(base_yaw + dyaw)
        if not ik.reachable(nx, y, nz):
            continue
        alt = ik.solve(nx, y, nz)
        alt["j5"] = grip
        if not ik.collides(alt, scene.obstacles):
            return alt, f"re-routed ({dyaw_deg:+d} deg) to avoid obstacle"

    # 2) try approaching from a higher hover then straight down
    for extra in (8.0, 14.0, 20.0):
        alt = ik.solve(x, y + extra, z)
        alt["j5"] = grip
        if not ik.collides(alt, scene.obstacles):
            return alt, f"raised approach (+{extra:.0f}cm) to avoid obstacle"

    return None, f"no collision-free path for '{action}'"


# =============================================================================
# MOTION  (smooth 30 fps interpolation, mid-motion collision guard)
# =============================================================================
def interpolate(a, b, n=30):
    keys = set(a) | set(b)
    return [{k: a.get(k, 0.0) + (b.get(k, 0.0) - a.get(k, 0.0)) * (i / n) for k in keys}
            for i in range(1, n + 1)]


def send_motion(sock, scene, current, target_angles, wait):
    frames = interpolate(current, target_angles, n=30)
    dt = wait / 30.0
    for f in frames:
        if ik.collides(f, scene.obstacles):
            print("[MOTION] aborted mid-path: frame collides")
            return current, False
        # flip rotation sign for Omniverse's convention
        out = {
            "j0": f.get("j0", 0.0),
            "j1": -f.get("j1", 0.0),
            "j2": -f.get("j2", 0.0),
            "j3": -f.get("j3", 0.0),
            "j4": f.get("j4", 0.0),
            "j5": f.get("j5", 0.3),
        }
        sock.send_json(out)
        time.sleep(dt)
    return dict(target_angles), True


# =============================================================================
# REPL
# =============================================================================
def main():
    ctx  = zmq.Context()
    cmd  = ctx.socket(zmq.PUSH)
    cmd.connect(f"tcp://localhost:{ZMQ_PORT_CMD}")
    scene = SceneState(ctx)

    time.sleep(0.3)
    scene.refresh()
    print(f"[ZMQ] cmd :{ZMQ_PORT_CMD}  state :{ZMQ_PORT_STATE}")
    print(f"[SCENE] {'LIVE from Omniverse' if scene.live else 'FALLBACK (socket silent)'}")
    print(f"[SCENE] target={scene.target}  obstacles={len(scene.obstacles)}")
    print("Commands: 'pick up the ball', 'go home', 'lift it', 'drop it'")
    print("          'scene' (show state), 'quit'\n")

    current = dict(HOME)

    while True:
        try:
            command = input("Command: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not command:
            continue
        if command.lower() == "quit":
            break
        if command.lower() == "scene":
            scene.refresh()
            print(f"  live={scene.live}  target={scene.target}")
            for o in scene.obstacles:
                print(f"  obstacle {o.get('name','?')}: ({o['x']},{o['y']},{o['z']}) r={o['r']}")
            print()
            continue

        scene.refresh()  # pull latest object positions before planning
        try:
            plan = ask_llm(command)
        except Exception as e:
            print(f"[Error] LLM: {e}\n")
            continue

        labels = [s.get("action", "home") for s in plan]
        print(f"[PLAN] {' -> '.join(labels)}")

        for step in plan:
            action = step.get("action", "home")
            wait   = float(step.get("wait", 1.0))
            angles, status = plan_angles(action, scene)
            if angles is None:
                print(f"[STOP] {action}: {status}")
                break
            if status != "ok":
                print(f"[ADAPT] {action}: {status}")
            current, ok = send_motion(cmd, scene, current, angles, wait)
            if not ok:
                print(f"[STOP] motion aborted at '{action}'")
                break
        print("[Done]\n")

    cmd.close()
    scene.sock.close()
    ctx.term()


if __name__ == "__main__":
    main()
