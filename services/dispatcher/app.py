import os
import time

import httpx
import zmq
from fastapi import FastAPI

from services.shared.schemas import DispatchRequest, DispatchResponse

ACTUATION_URL = os.environ.get(
    "ACTUATION_URL",
    "http://actuation:8040/actuate",
)

# sim-bridge (Omniverse Kit extension) BINDS on this address; we CONNECT to it.
# In compose, use host.docker.internal to reach the host-side sim.
SIM_BRIDGE_ADDR = os.environ.get(
    "SIM_BRIDGE_ADDR",
    "tcp://host.docker.internal:5556",
)

FRAMES_PER_DISPATCH = 30
FRAME_INTERVAL_S = 1.0 / 30.0

app = FastAPI(title="Dispatcher Service", version="1.0")

current_joints: list[float] = [0.0] * 6

context: zmq.Context | None = None
socket: zmq.Socket | None = None


@app.on_event("startup")
def _startup_zmq() -> None:
    global context, socket
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(SIM_BRIDGE_ADDR)


@app.on_event("shutdown")
def _shutdown_zmq() -> None:
    global socket, context
    if socket is not None:
        socket.close()
        socket = None
    if context is not None:
        context.term()
        context = None


def interpolate(start: list[float], target: list[float]) -> list[list[float]]:
    frames = []
    denom = FRAMES_PER_DISPATCH - 1
    for i in range(FRAMES_PER_DISPATCH):
        frame = [s + (t - s) * (i / denom) for s, t in zip(start, target)]
        frames.append(frame)
    return frames


@app.post("/dispatch", response_model=DispatchResponse)
def dispatch(request: DispatchRequest) -> DispatchResponse:
    global current_joints

    if socket is None:
        raise RuntimeError("Dispatcher ZMQ socket not initialised")

    target = list(request.joints)
    frames = interpolate(current_joints, target)

    for frame_id, frame in enumerate(frames):
        socket.send_json({"joints": frame, "frame_id": frame_id})
        time.sleep(FRAME_INTERVAL_S)

    current_joints = target

    # Run validated in sim — trigger actuation to publish MQTT.
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(ACTUATION_URL, json={"joints": target})
            response.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[dispatcher] actuation call failed: {e}")

    return DispatchResponse(accepted=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
