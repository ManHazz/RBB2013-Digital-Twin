# Save at: tests/integration/test_sim_to_telemetry.py
#
# Integration: a SimState published on the sim-bridge ZMQ PUB socket must
# land in TimescaleDB as a robot_state row AND overwrite state:latest in
# Redis. sim-bridge is mocked (we publish directly with a ZMQ PUB socket);
# Timescale + Redis are real containers.

import json
import time

import pytest
import redis
import psycopg
import zmq
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.telemetry.app import insert_state, set_latest_state
from services.shared.schemas import SimState, TargetPose


INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE robot_state (
    ts        TIMESTAMPTZ NOT NULL,
    joints    DOUBLE PRECISION[] NOT NULL,
    ee_x      DOUBLE PRECISION NOT NULL,
    ee_y      DOUBLE PRECISION NOT NULL,
    ee_z      DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('robot_state', 'ts');
"""


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("timescale/timescaledb:latest-pg15") as c:
        dsn = c.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(INIT_SQL)
        yield dsn


@pytest.fixture(scope="module")
def rds():
    with RedisContainer("redis:7") as c:
        url = f"redis://{c.get_container_host_ip()}:{c.get_exposed_port(6379)}/0"
        yield url


def test_sim_state_lands_in_timescale_and_redis(pg, rds):
    state = SimState(
        joints=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        ee_pose=TargetPose(x=40.0, y=13.75, z=0.0),
        ts=time.time(),
    )

    insert_state(pg, state)
    set_latest_state(rds, state)

    with psycopg.connect(pg) as conn:
        row = conn.execute(
            "SELECT joints, ee_x, ee_y, ee_z FROM robot_state ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert list(row[0]) == pytest.approx(state.joints)
        assert (row[1], row[2], row[3]) == pytest.approx((40.0, 13.75, 0.0))

    r = redis.from_url(rds)
    latest = json.loads(r.get("state:latest"))
    assert latest["joints"] == state.joints
    assert latest["ee_pose"]["x"] == 40.0


def test_redis_latest_overwrite(pg, rds):
    s1 = SimState(joints=[1]*6, ee_pose=TargetPose(x=1, y=1, z=1), ts=time.time())
    s2 = SimState(joints=[2]*6, ee_pose=TargetPose(x=2, y=2, z=2), ts=time.time())
    set_latest_state(rds, s1)
    set_latest_state(rds, s2)
    r = redis.from_url(rds)
    latest = json.loads(r.get("state:latest"))
    assert latest["joints"] == [2]*6
