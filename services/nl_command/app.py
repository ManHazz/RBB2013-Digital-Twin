import json
import os
import re

import httpx
from fastapi import FastAPI, HTTPException

from services.shared.schemas import CommandRequest, TargetPose

app = FastAPI(title="nl-command")

# --- Ollama connection (env-overridable for container use) ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "host.docker.internal:11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

# --- fallback scene: nl-command has no live scene socket, so it uses the
# same fallback values llm_controller.py uses when its state socket is
# silent. Documented simplification, not a bug. ---
FALLBACK_TARGET = {"x": 40.0, "y": 1.75, "z": 0.0, "r": 1.75}

# --- reused verbatim from llm_controller.py ---
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


def action_target(action: str, target: dict = FALLBACK_TARGET):
    """Map an action to a target (x, y, z). Returns None for 'home'
    (no movement target) or an unrecognised action."""
    t = target
    if action == "above":
        return (t["x"], t["y"] + 12.0, t["z"])
    if action == "grab":
        return (t["x"], t["y"], t["z"])
    if action == "lift":
        return (t["x"], t["y"] + 25.0, t["z"])
    if action == "place":
        return (t["x"], t["y"], t["z"])
    return None


async def ask_llm(command: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"/no_think\nCommand: {command}",
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(502, f"ollama request failed: {e}")

    raw = repair_json(resp.json()["response"].strip())

    try:
        start, end = raw.find("["), raw.rfind("]") + 1
        parsed = json.loads(raw[start:end]) if start != -1 else json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(422, "cannot parse pose from LLM response")

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not parsed:
        raise HTTPException(422, "cannot parse pose from LLM response")
    return parsed


@app.post("/command", response_model=TargetPose)
async def command(req: CommandRequest) -> TargetPose:
    if not req.text.strip():
        raise HTTPException(422, "text must not be empty")

    plan = await ask_llm(req.text)

    for step in plan:
        action = step.get("action", "home")
        target = action_target(action)
        if target is not None:
            x, y, z = target
            return TargetPose(x=x, y=y, z=z)

    # every step resolved to "home" (or unrecognised) — no movement target
    raise HTTPException(422, "cannot parse pose from LLM response")


@app.get("/health")
async def health():
    return {"status": "ok"}