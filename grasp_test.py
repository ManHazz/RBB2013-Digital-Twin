# =============================================================================
# grasp_test.py
# Grasp accuracy + precision test harness for the xlerobot IK.
#
# Spawns N random target positions across the arm's workspace, solves IK for
# each, and measures how close the gripper tip lands (via forward kinematics).
# Reports:
#   - per-target distance error (cm)
#   - overall success rate (within a tolerance)
#   - mean / median / max / std of error  (accuracy + precision)
#   - how many targets were unreachable
#   - how many collided with obstacles
#
# This runs PURELY on the math (robot_ik) — it does not need Omniverse running,
# so you can validate the IK quality offline and put the numbers in your report.
# =============================================================================
import math
import random
import statistics

import robot_ik as ik

# tolerance for a "successful" grasp: gripper tip within this distance of target
SUCCESS_TOL_CM = 1.0

# same obstacles as the scene (keep in sync with extension.py)
OBSTACLES = [
    {"name": "obstacle_A", "x": 25.0, "y": 12.0, "z": 8.0,  "r": 4.0},
    {"name": "obstacle_B", "x": 30.0, "y": 20.0, "z": -10.0, "r": 5.0},
]


def random_target():
    """A random reachable-ish point on/near the ground in front of the arm."""
    # sample in cylindrical coords so points spread over the workspace
    horiz = random.uniform(18.0, 55.0)
    yaw   = random.uniform(-math.pi / 2, math.pi / 2)  # front hemisphere
    y     = random.uniform(1.5, 8.0)                    # near the ground
    x = horiz * math.cos(yaw)
    z = horiz * math.sin(yaw)
    return (round(x, 2), round(y, 2), round(z, 2))


def run(n=200, seed=42, check_collisions=True):
    random.seed(seed)

    errors = []
    successes = 0
    unreachable = 0
    collided = 0
    rows = []

    for i in range(n):
        x, y, z = random_target()

        if not ik.reachable(x, y, z):
            unreachable += 1
            rows.append((x, y, z, None, "unreachable"))
            continue

        angles = ik.solve(x, y, z)
        tip = ik.gripper_tip(angles)
        err = math.sqrt((x - tip[0])**2 + (y - tip[1])**2 + (z - tip[2])**2)

        status = "ok"
        if check_collisions and ik.collides({**angles, "j5": 0.0}, OBSTACLES):
            collided += 1
            status = "collision"

        errors.append(err)
        if err <= SUCCESS_TOL_CM and status == "ok":
            successes += 1
        rows.append((x, y, z, err, status))

    # -------- report --------
    print("=" * 60)
    print(f"GRASP ACCURACY TEST   (n={n}, tol={SUCCESS_TOL_CM}cm)")
    print("=" * 60)
    print(f"Reachable targets:     {len(errors)}/{n}")
    print(f"Unreachable (skipped): {unreachable}")
    if check_collisions:
        print(f"Collided w/ obstacle:  {collided}")
    print(f"Successful grasps:     {successes}/{len(errors)}"
          f"  ({100*successes/max(1,len(errors)):.1f}%)")
    print("-" * 60)
    if errors:
        print("Tip-to-target error (cm):")
        print(f"  mean   : {statistics.mean(errors):.3f}")
        print(f"  median : {statistics.median(errors):.3f}")
        print(f"  std    : {statistics.pstdev(errors):.3f}   <- precision")
        print(f"  min    : {min(errors):.3f}")
        print(f"  max    : {max(errors):.3f}")
    print("=" * 60)

    # worst 5 for inspection
    bad = sorted([r for r in rows if r[3] is not None], key=lambda r: -r[3])[:5]
    print("Worst 5 targets by error:")
    for x, y, z, e, s in bad:
        print(f"  ({x:6.1f},{y:5.1f},{z:6.1f})  err={e:6.3f}cm  [{s}]")
    print()

    return errors


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    run(n=n)
