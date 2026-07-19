#!/usr/bin/env python3
# robot_arm_sender.py
# Sends joint angles (radians) to RobotArmExt via ZeroMQ PUSH.
# pip install pyzmq
#
# Usage:
#   python robot_arm_sender.py                        # default host 0.0.0.1:5556
#   python robot_arm_sender.py --host 10.32.3.55 --port 5556
#   python robot_arm_sender.py --mode sweep           # smooth joint sweep demo
#   python robot_arm_sender.py --mode wave            # wave motion demo
#   python robot_arm_sender.py --mode manual          # interactive manual input
 
import argparse
import json
import math
import time
import zmq
 
# =============================================================================
# JOINT ANGLE GENERATOR FUNCTIONS
# Each returns a dict: {"j0":float, "j1":float, ..., "j5":float}
# All angles in radians. t = elapsed time in seconds.
# Replace or extend these for PINO output.
# =============================================================================
 
# --- joint angle limits (radians) for reference ---
J0_LIMIT  = math.pi          # base:          -180 to +180 deg
J1_LIMIT  = math.pi / 2      # shoulder:       -90 to  +90 deg
J2_LIMIT  = math.pi * 0.75   # elbow:         -135 to +135 deg
J3_LIMIT  = math.pi / 2      # wrist pitch:    -90 to  +90 deg
J4_LIMIT  = math.pi          # wrist roll:    -180 to +180 deg
J5_MAX    = 0.5              # gripper:           0 (closed) to 0.5 rad open
 
 
def joints_sweep(t: float) -> dict:
    # each joint sweeps at a slightly different frequency for visual interest
    return {
        "j0": J0_LIMIT  * math.sin(t * 0.3),
        "j1": J1_LIMIT  * math.sin(t * 0.5) * 0.6,
        "j2": J2_LIMIT  * math.sin(t * 0.7 + 1.0) * 0.5,
        "j3": J3_LIMIT  * math.sin(t * 0.9 + 2.0) * 0.4,
        "j4": J4_LIMIT  * math.sin(t * 1.1),
        "j5": J5_MAX    * (0.5 + 0.5 * math.sin(t * 1.5)),   # 0 -> open -> 0
    }
 
 
def joints_wave(t: float) -> dict:
    # base rotates slowly, arm rises and falls like a wave
    phase = t * 0.4
    return {
        "j0": math.sin(t * 0.2) * J0_LIMIT * 0.5,
        "j1": math.sin(phase)           *  0.6,
        "j2": math.sin(phase + 1.05)    * -0.8,
        "j3": math.sin(phase + 2.09)    *  0.5,
        "j4": t * 0.5 % (2 * math.pi) - math.pi,   # continuous roll
        "j5": J5_MAX * (0.5 + 0.5 * math.cos(t)),
    }
 
 
# =============================================================================
# PLACEHOLDER FOR PINO / EXTERNAL SOLVER OUTPUT
# Replace the body of this function with your model's inference output.
# Input:  t  (float) -- simulation time in seconds
# Output: dict of j0..j5 in radians
# =============================================================================
def joints_from_pino(t: float) -> dict:
    # TODO: load your PINO model and call it here
    # e.g.:
    #   pred = pino_model.predict(t)  # returns array [j0,j1,j2,j3,j4,j5]
    #   return {f"j{i}": float(pred[i]) for i in range(6)}
    #
    # Stub: falls back to sweep so the visualiser is not empty
    return joints_sweep(t)
 
 
# =============================================================================
 
def send_angles(sock: zmq.Socket, angles: dict) -> None:
    sock.send_json(angles)
 
 
def mode_sweep(sock, hz, duration):
    interval = 1.0 / hz
    t0 = time.time()
    t_end = t0 + duration if duration > 0 else float("inf")
    print(f"[sender] sweep mode  hz={hz}  duration={'inf' if duration<=0 else duration}s")
    while time.time() < t_end:
        t = time.time() - t0
        angles = joints_sweep(t)
        send_angles(sock, angles)
        _print_angles(t, angles)
        time.sleep(interval)
 
 
def mode_wave(sock, hz, duration):
    interval = 1.0 / hz
    t0 = time.time()
    t_end = t0 + duration if duration > 0 else float("inf")
    print(f"[sender] wave mode  hz={hz}  duration={'inf' if duration<=0 else duration}s")
    while time.time() < t_end:
        t = time.time() - t0
        angles = joints_wave(t)
        send_angles(sock, angles)
        _print_angles(t, angles)
        time.sleep(interval)
 
 
def mode_manual(sock):
    print("[sender] manual mode - enter 6 angles in degrees: j0 j1 j2 j3 j4 j5")
    print("         press Ctrl+C to quit")
    while True:
        try:
            raw = input("angles> ").strip()
            if not raw:
                continue
            vals = [math.radians(float(v)) for v in raw.split()]
            if len(vals) != 6:
                print("  need exactly 6 values")
                continue
            angles = {f"j{i}": vals[i] for i in range(6)}
            send_angles(sock, angles)
            print(f"  sent: {[round(math.degrees(v),1) for v in vals]} deg")
        except KeyboardInterrupt:
            break
        except ValueError:
            print("  invalid input")
 
 
def _print_angles(t, angles):
    vals = "  ".join(f"j{i}={math.degrees(angles[f'j{i}']):.1f}°" for i in range(6))
    print(f"  t={t:6.2f}s  {vals}")
 
 
def main():
    parser = argparse.ArgumentParser(description="Robot arm ZMQ joint angle sender")
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int,   default=5556)
    parser.add_argument("--mode",     default="sweep",
                        choices=["sweep", "wave", "manual", "pino"])
    parser.add_argument("--hz",       type=float, default=30.0,
                        help="send rate in Hz")
    parser.add_argument("--duration", type=float, default=0,
                        help="run time in seconds (0 = infinite)")
    args = parser.parse_args()
 
    ctx  = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    addr = f"tcp://{args.host}:{args.port}"
    sock.connect(addr)
    time.sleep(0.1)   # let ZMQ establish connection
    print(f"[sender] connected to {addr}  mode={args.mode}")
 
    try:
        if args.mode == "sweep":
            mode_sweep(sock, args.hz, args.duration)
        elif args.mode == "wave":
            mode_wave(sock, args.hz, args.duration)
        elif args.mode == "manual":
            mode_manual(sock)
        elif args.mode == "pino":
            # placeholder: same loop as sweep but calls joints_from_pino
            interval = 1.0 / args.hz
            t0 = time.time()
            t_end = t0 + args.duration if args.duration > 0 else float("inf")
            print(f"[sender] pino mode  hz={args.hz}")
            while time.time() < t_end:
                t = time.time() - t0
                angles = joints_from_pino(t)
                send_angles(sock, angles)
                _print_angles(t, angles)
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[sender] interrupted")
 
    print("[sender] done")
    sock.close()
    ctx.term()
 
 
if __name__ == "__main__":
    main()
