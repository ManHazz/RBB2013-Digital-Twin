import json
import time

import psycopg
import pytest
import redis as redis_lib
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.shared.schemas import SimState, TargetPose
from services.telemetry.app import insert_state, set_latest_state, REDIS_LATEST_KEY

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

@pytest.fixture(scope="module")
def redis_url():
    with RedisContainer() as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


def test_redis_latest_state_overwrites(redis_url):
    """Confirms Redis holds only the latest state — proves state persistence
    (as opposed to Timescale's full history)."""
    client = redis_lib.Redis.from_url(redis_url)

    first = _fake_state()
    set_latest_state(client, first)
    stored = json.loads(client.get(REDIS_LATEST_KEY))
    assert stored["joints"] == pytest.approx(first.joints)

    second = _fake_state()
    second.joints[0] = 9.9
    set_latest_state(client, second)
    stored = json.loads(client.get(REDIS_LATEST_KEY))

    # latest write wins — key holds second's data, not first's
    assert stored["joints"][0] == pytest.approx(9.9)
    assert stored["joints"] != pytest.approx(first.joints)