import json
import zmq
import paho.mqtt.client as mqtt

# MQTT setup
client = mqtt.Client()
client.connect("localhost", 1883, 60)

# ZMQ setup
context = zmq.Context()
socket = context.socket(zmq.PULL)
socket.connect("tcp://localhost:5556")

print("Actuation Service Started...")

while True:

    message = socket.recv_json()

    print(f"Received frame {message['frame_id']}")

    client.publish(
        "robot/joints",
        json.dumps(message)
    )

    print(
        f"Published frame {message['frame_id']} to MQTT"
    )