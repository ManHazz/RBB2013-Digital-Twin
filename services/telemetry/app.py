"""Telemetry service.

Daemon-style — no HTTP surface. Subscribes to sim-bridge's published
state over ZMQ, then fans each SimState reading out to two sinks:

  - TimescaleDB (`robot_state` hypertable) — durable history
  - Redis (`state:latest` key) — fast-read latest-state cache

insert_state() and set_latest_state() are kept as standalone functions
(not buried in the loop) so they can be unit tested directly against
real Postgres/Redis test containers, without needing a live ZMQ feed.
"""
import os

import psycopg
import redis as redis_lib
import zmq

from services.shared.schemas import SimState

PG_DSN = os.environ.get(
    "PG_DSN", "postgresql://postgres:postgres@timescaledb:5432/postgres"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
SIM_STATE_ADDR = os.environ.get("SIM_STATE_ADDR", "tcp://sim-bridge:5557")

REDIS_LATEST_KEY = "state:latest"


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
            state = SimState.model_validate(raw)
            insert_state(conn, state)
            set_latest_state(redis_client, state)
        except Exception as exc:  # noqa: BLE001 - daemon must survive one bad message
            print(f"[telemetry] error processing message: {exc}")
            continue


if __name__ == "__main__":
    run()