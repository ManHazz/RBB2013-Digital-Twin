import json
from unittest.mock import Mock


def test_mqtt_publish():

    mqtt_client = Mock()

    message = {
        "joints": [
            10,
            20,
            30,
            40,
            50,
            60
        ],
        "frame_id": 5
    }


    mqtt_client.publish(
        "robot/joints",
        json.dumps(message)
    )


    mqtt_client.publish.assert_called_once()


    topic, payload = (
        mqtt_client.publish.call_args[0]
    )


    assert topic == "robot/joints"


    data = json.loads(payload)


    assert data["frame_id"] == 5

    assert data["joints"] == [
        10,
        20,
        30,
        40,
        50,
        60
    ]