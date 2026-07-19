#!/usr/bin/env python3
# spiral_sender.py
# Pushes sphere positions to the SphereCylinderExt via ZeroMQ PUSH socket.
# pip install pyzmq
#
# Usage:
#   python spiral_sender.py                          # default: 10.32.3.55:5555
#   python spiral_sender.py --host 10.32.3.55 --port 5555
#   python spiral_sender.py --steps 300 --hz 30
 
import argparse
import json
import math
import time
import zmq
 
# --- spiral motion parameters ---
ORBIT_RADIUS_START = 5.0    # cm  inner start of spiral
ORBIT_RADIUS_END   = 35.0   # cm  outer end  (keep < ~39 cm inner wall)
ORBIT_HEIGHT_START = 6.0    # cm  Y floor  (= SPHERE_RADIUS)
ORBIT_HEIGHT_END   = 30.0   # cm  Y ceiling (keep < CYLINDER_HEIGHT 40 cm)
SPIRAL_TURNS       = 3.0    # full circles over total steps
 
# 3 spheres evenly spread 120 deg apart
PHASE_OFFSETS = [0.0, 2.0944, 4.1888]
 
 
def spiral_positions(step: int, total_steps: int) -> list:
    t      = step / max(total_steps - 1, 1)  # 0.0 -> 1.0
    radius = ORBIT_RADIUS_START + (ORBIT_RADIUS_END - ORBIT_RADIUS_START) * t
    height = ORBIT_HEIGHT_START + (ORBIT_HEIGHT_END - ORBIT_HEIGHT_START) * t
    angle  = 2.0 * math.pi * SPIRAL_TURNS * t
 
    positions = []
    for phase in PHASE_OFFSETS:
        theta = angle + phase
        positions.append([
            round(radius * math.cos(theta), 4),
            round(height, 4),
            round(radius * math.sin(theta), 4),
        ])
    return positions
 
 
def main():
    parser = argparse.ArgumentParser(description="ZMQ spiral sphere sender")
    parser.add_argument("--host",  default="127.0.0.1")
    parser.add_argument("--port",  type=int,   default=5555)
    parser.add_argument("--steps", type=int,   default=200)
    parser.add_argument("--hz",    type=float, default=24.0)
    args = parser.parse_args()
 
    ctx  = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    # PUSH connects to the Kit PULL socket
    addr = f"tcp://{args.host}:{args.port}"
    sock.connect(addr)
    # give ZMQ a moment to establish the connection before first send
    time.sleep(0.1)
 
    interval = 1.0 / args.hz
    print(f"[sender] connected to {addr}")
    print(f"[sender] {args.steps} steps @ {args.hz} hz  ({args.steps / args.hz:.1f}s total)")
 
    for step in range(args.steps):
        positions = spiral_positions(step, args.steps)
        msg = {"positions": positions}
        sock.send_json(msg)
        print(f"  step {step:04d}  sphere0={positions[0]}")
        time.sleep(interval)
 
    print("[sender] done")
    sock.close()
    ctx.term()
 
 
if __name__ == "__main__":
    main()
