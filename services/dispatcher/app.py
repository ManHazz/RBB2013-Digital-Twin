from fastapi import FastAPI
from services.shared.schemas import (
    DispatchRequest,
    DispatchResponse,
)

import zmq
import time

app = FastAPI(
    title="Dispatcher Service",
    version="1.0"
)

# Remember robot's last position
current_joints = [0, 0, 0, 0, 0, 0]

# ZMQ setup
context = zmq.Context()
socket = context.socket(zmq.PUSH)
socket.bind("tcp://*:5556")


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

    current_joints = target

    return DispatchResponse(
        accepted=True
    )