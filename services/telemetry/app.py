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


def run() -> None:
    """Daemon loop: SUB on sim-bridge state. (Writes not wired up yet.)"""
    conn = psycopg.connect(PG_DSN)
    redis_client = redis_lib.Redis.from_url(REDIS_URL)

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(SIM_STATE_ADDR)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    print(f"[telemetry] subscribed to {SIM_STATE_ADDR}")

    while True:
        raw = sub.recv_json()
        state = SimState.model_validate(raw)
        print(f"[telemetry] received state: {state}")


if __name__ == "__main__":
    run()