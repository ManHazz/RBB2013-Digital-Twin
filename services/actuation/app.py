import json
import os

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException

from services.shared.schemas import ActuationCommand

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = "xlerobot/cmd"

app = FastAPI(title="actuation")

_client: mqtt.Client | None = None


@app.on_event("startup")
def _connect_mqtt() -> None:
    global _client
    _client = mqtt.Client()
    _client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    _client.loop_start()


@app.on_event("shutdown")
def _disconnect_mqtt() -> None:
    if _client is not None:
        _client.loop_stop()
        _client.disconnect()


@app.post("/actuate")
def actuate(cmd: ActuationCommand) -> dict:
    if _client is None:
        raise HTTPException(503, "MQTT client not initialised")

    payload = json.dumps({
        "joints": cmd.joints
    })

    result = _client.publish(MQTT_TOPIC, payload)

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(
            502,
            f"MQTT publish failed: rc={result.rc}"
        )

    return {
        "published": True,
        "topic": MQTT_TOPIC
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok"
    }