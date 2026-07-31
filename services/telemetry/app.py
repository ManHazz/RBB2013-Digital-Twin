"""Telemetry service.

Daemon-style — no HTTP surface. Subscribes to sim-bridge's published
state over ZMQ, then fans each SimState reading out to two sinks:

  - TimescaleDB (`robot_state` hypertable) — durable history
  - Redis (`state:latest` key) — fast-read latest-state cache

insert_state() and set_latest_state() are kept as standalone functions
(not buried in the loop) so they can be unit tested directly against
real Postgres/Redis test containers, without needing a live ZMQ feed.

The sim-bridge (Kit extension) currently publishes a dict of
{target, obstacles, angles: {j0..j5}} rather than the SimState contract
shape. _normalize_from_sim() adapts that wire format to a SimState
so downstream storage can stay strictly typed.
"""
import os
import time

import psycopg
import redis as redis_lib
import zmq

from services.shared.schemas import SimState, TargetPose

PG_DSN = os.environ.get(
    "PG_DSN", "postgresql://postgres:postgres@timescaledb:5432/postgres"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
SIM_STATE_ADDR = os.environ.get("SIM_STATE_ADDR", "tcp://sim-bridge:5557")

REDIS_LATEST_KEY = "state:latest"

# Arm link lengths (cm) — must match extension.py and robot_ik.py.
_LINK_0 = 8.0
_LINK_1 = 30.0
_LINK_2 = 25.0
_LINK_3 = 15.0
_LINK_4 = 8.0


def insert_state(conn: psycopg.Connection, state: SimState) -> None:
    """Insert one SimState reading into the robot_state hypertable."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO robot_state (ts, joints, ee_x, ee_y, ee_z)
            VALUES (to_timestamp(%s), %s, %s, %s, %s)
            """,
            (
                state.ts,
                state.joints,
                state.ee_pose.x,
                state.ee_pose.y,
                state.ee_pose.z,
            ),
        )
    conn.commit()


def set_latest_state(redis_client: "redis_lib.Redis", state: SimState) -> None:
    """Overwrite the cached latest robot state in Redis (proves state persistence)."""
    redis_client.set(REDIS_LATEST_KEY, state.model_dump_json())


def _fk_gripper_position(joints: list[float]) -> TargetPose:
    """Approximate end-effector position from joint angles. Matches the
    kinematic chain sketch in extension.py (Y-up, cm). Used only when the
    sim-bridge publish payload does not include an ee_pose."""
    import math

    j0, j1, j2, j3, j4, _ = joints

    # planar reach along the arm (in the arm's rotated frame)
    r = 0.0
    y = _LINK_0
    a = 0.0
    for length, joint in ((_LINK_1, j1), (_LINK_2, j2), (_LINK_3, j3), (_LINK_4, j4)):
        a += joint
        r += length * math.sin(a)
        y += length * math.cos(a)

    x = r * math.cos(j0)
    z = -r * math.sin(j0)
    return TargetPose(x=x, y=y, z=z)


def _normalize_from_sim(raw: dict) -> SimState:
    """Accept both the SimState wire format and the sim-bridge legacy
    format (`{target, obstacles, angles: {j0..j5}}`), returning a
    SimState either way."""
    if "joints" in raw and "ee_pose" in raw and "ts" in raw:
        return SimState.model_validate(raw)

    angles = raw.get("angles", {}) or {}
    joints = [float(angles.get(f"j{i}", 0.0)) for i in range(6)]
    ts = float(raw.get("ts", time.time()))
    ee_pose = _fk_gripper_position(joints)
    return SimState(joints=joints, ee_pose=ee_pose, ts=ts)


def run() -> None:
    """Daemon loop: SUB on sim-bridge state, write to Timescale + Redis."""
    conn = psycopg.connect(PG_DSN)
    redis_client = redis_lib.Redis.from_url(REDIS_URL)

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(SIM_STATE_ADDR)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    print(f"[telemetry] subscribed to {SIM_STATE_ADDR}, writing to Timescale + Redis")

    while True:
        try:
            raw = sub.recv_json()
            state = _normalize_from_sim(raw)
            insert_state(conn, state)
            set_latest_state(redis_client, state)
        except Exception as exc:  # noqa: BLE001 - daemon must survive one bad message
            print(f"[telemetry] error processing message: {exc}")
            continue


if __name__ == "__main__":
    run()
