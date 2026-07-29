import os
import re

import httpx
from fastapi import FastAPI, HTTPException

from services.shared.schemas import CommandRequest, TargetPose

app = FastAPI(title="nl-command")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "host.docker.internal:11434")


def parse_pose_from_text(text: str) -> TargetPose:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(numbers) < 3:
        raise ValueError(f"could not find 3 floats in: {text!r}")
    x, y, z = (float(n) for n in numbers[:3])
    return TargetPose(x=x, y=y, z=z)


@app.post("/command", response_model=TargetPose)
async def command(req: CommandRequest) -> TargetPose:
    if not req.text.strip():
        raise HTTPException(422, "text must not be empty")

    prompt = (
        "You control a robot arm. Given an instruction, respond with "
        "ONLY three numbers separated by spaces representing the target "
        f"x y z position. Instruction: {req.text}"
    )

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"http://{OLLAMA_HOST}/api/generate",
                json={"model": "llama3", "prompt": prompt, "stream": False},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(502, f"ollama request failed: {e}")

    completion = resp.json().get("response", "")

    try:
        return parse_pose_from_text(completion)
    except ValueError:
        raise HTTPException(422, "cannot parse pose from LLM response")


@app.get("/health")
async def health():
    return {"status": "ok"}