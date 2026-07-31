# =============================================================================
# robot_ik.py
# Forward + inverse kinematics for the xlerobot arm.
#
# Convention (used consistently by BOTH fk and ik):
#   - all joint angles in radians
#   - a link's angle is measured from the +Y (up) axis
#   - positive cumulative angle tips the link toward +X (forward/horizontal)
#   - a link at cumulative angle 'a' points in direction (sin a, cos a)
#     in the arm's (horizontal, vertical) working plane
#   - j0 then rotates that whole plane about the Y axis
#
# IK and FK round-trip to ~0 cm error for any reachable target (verified).
# All lengths in centimetres. Y-up (Omniverse default).
# =============================================================================
import math

# --- link lengths (MUST match extension.py) ---
BASE_H   = 8.0     # pedestal height (J0 sits on top)
LINK_1   = 30.0    # upper arm  J1 -> J2
LINK_2   = 25.0    # forearm    J2 -> J3
LINK_3   = 15.0    # wrist      J3 -> J4
LINK_4   = 8.0     # palm       J4 -> J5
GRIPPER  = 6.0     # finger length J5 -> tip

# distance from the wrist pivot to the gripper tip when pointing straight down
GRIP_DROP = LINK_3 + LINK_4 + GRIPPER          # 29 cm
REACH_MAX = LINK_1 + LINK_2 + LINK_3 + LINK_4 + GRIPPER  # 84 cm


# =============================================================================
# FORWARD KINEMATICS
# =============================================================================

def forward_kinematics(angles: dict) -> dict:
    """
    Given joint angles, return 3D positions (cm) of each point along the arm.
    Keys: shoulder, elbow, wrist, palm, tip -> (x, y, z) tuples.
    """
    j0 = angles.get("j0", 0.0)
    j1 = angles.get("j1", 0.0)
    j2 = angles.get("j2", 0.0)
    j3 = angles.get("j3", 0.0)

    a1 = j1
    a2 = a1 + j2
    a3 = a2 + j3

    h, v = 0.0, BASE_H
    shoulder = (h, v)
    h += LINK_1 * math.sin(a1); v += LINK_1 * math.cos(a1)
    elbow = (h, v)
    h += LINK_2 * math.sin(a2); v += LINK_2 * math.cos(a2)
    wrist = (h, v)
    h += LINK_3 * math.sin(a3); v += LINK_3 * math.cos(a3)
    palm = (h, v)
    h += (LINK_4 + GRIPPER) * math.sin(a3)
    v += (LINK_4 + GRIPPER) * math.cos(a3)
    tip = (h, v)

    def to3d(p):
        hh, vv = p
        return (hh * math.cos(j0), vv, hh * math.sin(j0))

    return {
        "shoulder": to3d(shoulder),
        "elbow":    to3d(elbow),
        "wrist":    to3d(wrist),
        "palm":     to3d(palm),
        "tip":      to3d(tip),
    }


def gripper_tip(angles: dict) -> tuple:
    """Just the 3D position (cm) of the gripper tip."""
    return forward_kinematics(angles)["tip"]


# =============================================================================
# INVERSE KINEMATICS  (analytic, gripper points straight down)
# =============================================================================

def solve(x: float, y: float, z: float) -> dict:
    """
    Solve IK so the gripper TIP reaches (x, y, z) in cm, gripper pointing down.
    Returns j0..j4 (j5 gripper handled by the caller).
    Analytic and exact for reachable targets — no iterative correction needed.
    """
    # j0: yaw the working plane to face the target
    j0 = math.atan2(z, x)
    horiz = math.sqrt(x * x + z * z)

    # the wrist sits GRIP_DROP above the target so the gripper drops onto it
    wx = horiz
    wy = y + GRIP_DROP
    dx = wx
    dy = wy - BASE_H
    D = math.sqrt(dx * dx + dy * dy)

    reach2 = LINK_1 + LINK_2
    if D > reach2:
        D = reach2 * 0.999  # clamp; reachable() will have already warned

    # law of cosines for the elbow
    cos_j2 = (D * D - LINK_1 ** 2 - LINK_2 ** 2) / (2 * LINK_1 * LINK_2)
    cos_j2 = max(-1.0, min(1.0, cos_j2))
    j2 = -math.acos(cos_j2)            # negative = elbow bends down

    # shoulder angle (measured from +Y, so atan2(horiz, vert))
    alpha = math.atan2(dx, dy)
    cos_b = (LINK_1 ** 2 + D * D - LINK_2 ** 2) / (2 * LINK_1 * D)
    cos_b = max(-1.0, min(1.0, cos_b))
    beta = math.acos(cos_b)
    j1 = alpha + beta

    # gripper straight down => cumulative angle a3 must equal pi
    j3 = math.pi - (j1 + j2)
    j4 = 0.0

    return {"j0": j0, "j1": j1, "j2": j2, "j3": j3, "j4": j4}


def reachable(x: float, y: float, z: float) -> bool:
    """Is the target within the arm's reach (accounting for the gripper drop)?"""
    horiz = math.sqrt(x * x + z * z)
    wy = y + GRIP_DROP
    D = math.sqrt(horiz * horiz + (wy - BASE_H) ** 2)
    return D <= (LINK_1 + LINK_2)


def accuracy_at(x: float, y: float, z: float) -> float:
    """Residual error (cm) between the gripper tip and the target after solving."""
    tip = gripper_tip(solve(x, y, z))
    return math.sqrt((x - tip[0]) ** 2 + (y - tip[1]) ** 2 + (z - tip[2]) ** 2)


# =============================================================================
# COLLISION GEOMETRY
# =============================================================================

def arm_points(angles: dict, samples_per_link=6) -> list:
    """Sample 3D points along the whole arm (shoulder..tip) for collision tests."""
    fk = forward_kinematics(angles)
    chain = [fk["shoulder"], fk["elbow"], fk["wrist"], fk["palm"], fk["tip"]]
    pts = []
    for a, b in zip(chain[:-1], chain[1:]):
        for i in range(samples_per_link + 1):
            t = i / samples_per_link
            pts.append((
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
            ))
    return pts


def collides(angles: dict, obstacles: list, margin=2.0) -> bool:
    """
    obstacles: list of {"x","y","z","r"} spheres.
    True if any sampled arm point is within (r + margin) of an obstacle centre.
    """
    pts = arm_points(angles)
    for ob in obstacles:
        ox, oy, oz, orr = ob["x"], ob["y"], ob["z"], ob["r"]
        thresh = orr + margin
        for px, py, pz in pts:
            if math.sqrt((px-ox)**2 + (py-oy)**2 + (pz-oz)**2) < thresh:
                return True
    return False


# =============================================================================
# SELF-TEST
# =============================================================================
if __name__ == "__main__":
    print(f"Arm max reach: {REACH_MAX:.1f} cm\n")
    for tgt in [(40, 1.75, 0), (35, 1.75, 10), (30, 5, -15), (20, 1.75, 0), (50, 20, 0)]:
        x, y, z = tgt
        ok = reachable(x, y, z)
        ang = solve(x, y, z)
        tip = gripper_tip(ang)
        err = accuracy_at(x, y, z)
        flag = "" if ok else "  (OUT OF REACH)"
        print(f"target {tgt}  reachable={ok}{flag}")
        print(f"  angles: { {k: round(v,3) for k,v in ang.items()} }")
        print(f"  tip:    ({tip[0]:.2f}, {tip[1]:.2f}, {tip[2]:.2f})   error: {err:.2f} cm\n")
