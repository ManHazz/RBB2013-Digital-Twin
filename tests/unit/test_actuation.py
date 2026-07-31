import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import services.actuation.app as actuation_app


def test_actuate_publishes_to_correct_topic(monkeypatch):
    fake_client = MagicMock()
    fake_client.publish.return_value.rc = 0  # MQTT_ERR_SUCCESS

    monkeypatch.setattr(
        actuation_app,
        "_client",
        fake_client
    )

    client = TestClient(actuation_app.app)

    resp = client.post(
        "/actuate",
        json={
            "joints": [1, 2, 3, 4, 5, 6]
        }
    )

    assert resp.status_code == 200
    assert resp.json()["topic"] == "xlerobot/cmd"

    fake_client.publish.assert_called_once()

    topic, payload = fake_client.publish.call_args[0]

    assert topic == "xlerobot/cmd"
    assert json.loads(payload) == {
        "joints": [1, 2, 3, 4, 5, 6]
    }


def test_actuate_rejects_wrong_joint_count():

    client = TestClient(actuation_app.app)

    resp = client.post(
        "/actuate",
        json={
            "joints": [1, 2, 3]
        }
    )

    assert resp.status_code == 422