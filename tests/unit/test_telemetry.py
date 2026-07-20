"""Unit tests for the telemetry service's TimescaleDB write path.

Uses testcontainers to spin up a real timescale/timescaledb image,
applies infra/timescaledb/init.sql against it, then calls
insert_state() directly (no ZMQ, no daemon loop) and reads the row
back with a plain SELECT.

Requires Docker to be running locally:
    pip install pytest testcontainers psycopg[binary]
    pytest tests/unit/test_telemetry.py -k timescale
"""
import time

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from services.shared.schemas import SimState, TargetPose
from services.telemetry.app import insert_state

INIT_SQL_PATH = "infra/timescaledb/init.sql"


def _apply_init_sql(dsn: str) -> None:
    with open(INIT_SQL_PATH) as f:
        sql = f.read()
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def _fake_state() -> SimState:
    return SimState(
        joints=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        ee_pose=TargetPose(x=1.0, y=2.0, z=3.0),
        ts=time.time(),
    )


@pytest.fixture(scope="module")
def pg_dsn():
    with PostgresContainer("timescale/timescaledb:latest-pg16") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        _apply_init_sql(dsn)
        yield dsn


def test_insert_and_read(pg_dsn):
    state = _fake_state()

    with psycopg.connect(pg_dsn) as conn:
        insert_state(conn, state)

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT joints, ee_x, ee_y, ee_z FROM robot_state ORDER BY ts DESC LIMIT 1"
        )
        row = cur.fetchone()

    assert row is not None
    joints, ee_x, ee_y, ee_z = row
    assert list(joints) == pytest.approx(state.joints)
    assert ee_x == pytest.approx(state.ee_pose.x)
    assert ee_y == pytest.approx(state.ee_pose.y)
    assert ee_z == pytest.approx(state.ee_pose.z)