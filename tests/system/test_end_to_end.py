# Save at: tests/system/test_end_to_end.py
#
# System test: bring up the full compose stack, POST /command, assert a
# robot_state row lands in TimescaleDB with plausible joints.
#
# Prereq: `docker compose -f infra/docker-compose.yml up -d` before running.
# In CI this is orchestrated by the workflow's compose step.

import os
import time

import httpx
import psycopg
import pytest

NL_URL = os.environ.get("NL_URL", "http://localhost:8010")
PG_DSN = os.environ.get(
    "PG_DSN", "postgres://postgres:postgres@localhost:5432/robot"
)


@pytest.mark.system
def test_command_produces_timescale_row():
    baseline = _row_count()

    r = httpx.post(f"{NL_URL}/command", json={"text": "pick up the ball"}, timeout=30.0)
    assert r.status_code == 200, r.text

    # Wait up to 10s for sim tick → telemetry → insert
    for _ in range(20):
        if _row_count() > baseline:
            break
        time.sleep(0.5)

    with psycopg.connect(PG_DSN) as conn:
        row = conn.execute(
            "SELECT joints, ee_x, ee_y, ee_z FROM robot_state ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        assert row is not None, "no robot_state row inserted"
        joints = list(row[0])
        assert len(joints) == 6
        assert all(isinstance(j, float) for j in joints)


def _row_count() -> int:
    with psycopg.connect(PG_DSN) as conn:
        return conn.execute("SELECT count(*) FROM robot_state").fetchone()[0]
