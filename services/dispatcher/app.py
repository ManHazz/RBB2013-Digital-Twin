from fastapi import FastAPI
from services.shared.schemas import (
    DispatchRequest,
    DispatchResponse,
)

import zmq
import time
import os
import httpx

ACTUATION_URL = os.environ.get(
    "ACTUATION_URL",
    "http://localhost:8040/actuate"
)

app = FastAPI(
    title="Dispatcher Service",
    version="1.0"
)

# Remember robot's last position
current_joints = [0, 0, 0, 0, 0, 0]

# ZMQ setup
context: zmq.Context | None = None
socket: zmq.Socket | None = None

@app.on_event("startup")
def _startup_zmq() -> None:
    global context, socket

    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.bind("tcp://*:5556")


@app.on_event("shutdown")
def _shutdown_zmq() -> None:
    global socket, context

    if socket is not None:
        socket.close()

    if context is not None:
        context.term()

def interpolate(start, target):
    frames = []

    for i in range(30):

        frame = []

        for s, t in zip(start, target):

            value = s + (t - s) * (i / 29)
            frame.append(value)

        frames.append(frame)

    return frames

@app.post("/dispatch", response_model=DispatchResponse)
def dispatch(request: DispatchRequest):

    global current_joints

    if socket is None:
        raise RuntimeError("Dispatcher ZMQ socket not initialised")

    target = request.joints

    frames = interpolate(
        current_joints,
        target
    )

    for frame_id, frame in enumerate(frames):

        message = {
            "joints": frame,
            "frame_id": frame_id
        }

        socket.send_json(message)

        time.sleep(1 / 30)

    # Run validated — trigger actuation
    # Run validated — trigger actuation
        try:
            with httpx.Client(timeout=5.0) as client:
            response = client.post(
                ACTUATION_URL,
                json={"joints": target}
            )
            response.raise_for_status()

    except httpx.HTTPError as e:
        print(f"[dispatcher] actuation call failed: {e}")

        current_joints = target

        return DispatchResponse(
            accepted=True
        )