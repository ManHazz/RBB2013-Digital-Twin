# Save at: tests/integration/test_actuation_mqtt.py
#
# Integration: actuation POST /actuate must publish the contract topic
# xlerobot/cmd with the correct payload to a REAL mosquitto broker.
# Uses testcontainers to spin up mosquitto for the test session.

import json
import time

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer


@pytest.fixture(scope="module")
def mosquitto():
    container = (
        DockerContainer("eclipse-mosquitto:2")
        .with_command("mosquitto -c /mosquitto-no-auth.conf")
        .with_exposed_ports(1883)
    )
    container.start()
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(1883))
    time.sleep(1.0)
    yield host, port
    container.stop()


@pytest.fixture
def actuation_client(mosquitto, monkeypatch):
    host, port = mosquitto
    monkeypatch.setenv("MQTT_HOST", host)
    monkeypatch.setenv("MQTT_PORT", str(port))

    # import after env is set so module-level defaults pick it up
    from services.actuation import app as actuation_module
    # override module-level constants that were read at import time
    actuation_module.MQTT_HOST = host
    actuation_module.MQTT_PORT = port

    with TestClient(actuation_module.app) as client:
        yield client, host, port


def test_actuate_publishes_contract_topic(actuation_client):
    client, host, port = actuation_client

    received = []
    sub = mqtt.Client()

    def on_message(_c, _u, msg):
        received.append((msg.topic, msg.payload))

    sub.on_message = on_message
    sub.connect(host, port, keepalive=30)
    sub.subscribe("xlerobot/cmd")
    sub.loop_start()
    time.sleep(0.5)

    r = client.post("/actuate", json={"joints": [1, 2, 3, 4, 5, 6]})
    assert r.status_code == 200, r.text
    assert r.json() == {"published": True, "topic": "xlerobot/cmd"}

    # wait up to 2s for message delivery
    for _ in range(20):
        if received:
            break
        time.sleep(0.1)

    sub.loop_stop()
    sub.disconnect()

    assert received, "no MQTT message received on xlerobot/cmd"
    topic, payload = received[0]
    assert topic == "xlerobot/cmd"
    body = json.loads(payload)
    assert body["joints"] == [1, 2, 3, 4, 5, 6]


def test_actuate_rejects_wrong_joint_count(actuation_client):
    client, _, _ = actuation_client
    r = client.post("/actuate", json={"joints": [1, 2, 3]})
    assert r.status_code == 422
