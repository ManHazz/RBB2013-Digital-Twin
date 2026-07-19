# test_pose.py
import zmq, time, json

ctx = zmq.Context()
sock = ctx.socket(zmq.PUSH)
sock.connect("tcp://localhost:5556")

poses = {
    "home":     {"j0":0.0, "j1":0.0,  "j2":0.0,  "j3":0.0, "j4":0.0, "j5":0.3},
    "approach": {"j0":0.0, "j1":0.8,  "j2":-0.6, "j3":0.2, "j4":0.0, "j5":0.3},
    "grab":     {"j0":0.0, "j1":0.9,  "j2":-0.7, "j3":0.3, "j4":0.0, "j5":0.0},
    "lift":     {"j0":0.0, "j1":0.6,  "j2":-0.4, "j3":0.2, "j4":0.0, "j5":0.0},
}

while True:
    name = input("pose name (or custom j0-j5 values as JSON): ").strip()
    if name in poses:
        sock.send_json(poses[name])
        print(f"sent: {poses[name]}")
    else:
        try:
            sock.send_json(json.loads(name))
        except:
            print("unknown pose or bad JSON")