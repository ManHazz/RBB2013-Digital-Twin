import math
import json
import zmq
import omni.ext
import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdShade, Usd

# =============================================================================
# ARM GEOMETRY  (cm, Y-up)  -- MUST match robot_ik.py
# =============================================================================
BALL_RADIUS_BASE    = 4.0
BALL_RADIUS_J1      = 3.5
BALL_RADIUS_J2      = 3.0
BALL_RADIUS_J3      = 2.5
BALL_RADIUS_J4      = 2.5
BALL_RADIUS_GRIPPER = 2.0

LINK_0_HEIGHT  = 8.0
LINK_1_LENGTH  = 30.0
LINK_2_LENGTH  = 25.0
LINK_3_LENGTH  = 15.0
LINK_4_LENGTH  = 8.0
GRIPPER_LENGTH = 6.0
GRIPPER_SPREAD = 2.5
STICK_RADIUS   = 0.8

# =============================================================================
# SCENE OBJECTS  -- target ball + obstacles. Edit these freely.
# The extension publishes these positions so the controller can read them live.
# =============================================================================
TARGET_BALL = {"x": 40.0, "y": 1.75, "z": 0.0, "r": 1.75}

OBSTACLES = [
    {"name": "obstacle_A", "x": 25.0, "y": 12.0, "z": 8.0,  "r": 4.0},
    {"name": "obstacle_B", "x": 30.0, "y": 20.0, "z": -10.0, "r": 5.0},
]

# =============================================================================
# ZMQ
# =============================================================================
ZMQ_PORT_CMD   = 5556   # PULL: receive joint commands
ZMQ_PORT_STATE = 5557   # PUB:  publish scene + arm state
STATE_PERIOD   = 0.1    # seconds between state publishes (10 Hz)

# =============================================================================
# JOINT DEFAULTS (radians)
# =============================================================================
DEFAULT_ANGLES = {"j0": 0.0, "j1": 0.0, "j2": 0.0, "j3": 0.0, "j4": 0.0, "j5": 0.3}

# =============================================================================
# COLOURS
# =============================================================================
MAT_JOINT_COLOR    = Gf.Vec3f(0.15, 0.45, 0.80)
MAT_LINK_COLOR     = Gf.Vec3f(0.75, 0.75, 0.78)
MAT_GRIPPER_COLOR  = Gf.Vec3f(0.90, 0.55, 0.10)
MAT_BASE_COLOR     = Gf.Vec3f(0.20, 0.20, 0.22)
MAT_TARGET_COLOR   = Gf.Vec3f(0.85, 0.12, 0.12)   # red target ball
MAT_OBSTACLE_COLOR = Gf.Vec3f(0.55, 0.20, 0.75)   # purple obstacles


# =============================================================================
# HELPERS
# =============================================================================
def _get_or_create_stage() -> Usd.Stage:
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if stage is None:
        ctx.new_stage()
        stage = ctx.get_stage()
    return stage


def _make_material(stage, path, color, roughness=0.4, metallic=0.3):
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _bind(prim, mat):
    UsdShade.MaterialBindingAPI(prim).Bind(mat)


def _translate(prim, x, y, z):
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(x, y, z))


def _add_ball(stage, path, radius, mat):
    sp = UsdGeom.Sphere.Define(stage, path)
    sp.CreateRadiusAttr(radius)
    _bind(sp.GetPrim(), mat)
    return sp.GetPrim()


def _add_stick(stage, path, length, mat):
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(STICK_RADIUS)
    cyl.CreateHeightAttr(length)
    cyl.CreateAxisAttr(UsdGeom.Tokens.y)
    _bind(cyl.GetPrim(), mat)
    return cyl.GetPrim()


# =============================================================================
# SCENE BUILD
# =============================================================================
def build_scene_objects(stage):
    """Spawn the target ball and obstacles. Returns dict of prim handles."""
    root = "/World/Scene"
    UsdGeom.Xform.Define(stage, root)
    mp = f"{root}/Materials"
    m_target = _make_material(stage, f"{mp}/Target", MAT_TARGET_COLOR, 0.3, 0.0)
    m_obs    = _make_material(stage, f"{mp}/Obstacle", MAT_OBSTACLE_COLOR, 0.5, 0.1)

    handles = {}

    # target ball
    tb = UsdGeom.Xform.Define(stage, f"{root}/TargetBall")
    _add_ball(stage, f"{root}/TargetBall/Geo", TARGET_BALL["r"], m_target)
    _translate(tb.GetPrim(), TARGET_BALL["x"], TARGET_BALL["y"], TARGET_BALL["z"])
    handles["target"] = tb.GetPrim()

    # obstacles
    for ob in OBSTACLES:
        xf = UsdGeom.Xform.Define(stage, f"{root}/{ob['name']}")
        _add_ball(stage, f"{root}/{ob['name']}/Geo", ob["r"], m_obs)
        _translate(xf.GetPrim(), ob["x"], ob["y"], ob["z"])
        handles[ob["name"]] = xf.GetPrim()

    return handles


def build_robot(stage):
    root = "/World/RobotArm"
    UsdGeom.Xform.Define(stage, root)
    mp = f"{root}/Materials"
    m_joint   = _make_material(stage, f"{mp}/Joint",   MAT_JOINT_COLOR,   0.3, 0.6)
    m_link    = _make_material(stage, f"{mp}/Link",    MAT_LINK_COLOR,    0.5, 0.4)
    m_gripper = _make_material(stage, f"{mp}/Gripper", MAT_GRIPPER_COLOR, 0.4, 0.1)
    m_base    = _make_material(stage, f"{mp}/Base",    MAT_BASE_COLOR,    0.7, 0.2)

    ped = UsdGeom.Cylinder.Define(stage, f"{root}/Pedestal")
    ped.CreateRadiusAttr(BALL_RADIUS_BASE * 1.8)
    ped.CreateHeightAttr(LINK_0_HEIGHT)
    ped.CreateAxisAttr(UsdGeom.Tokens.y)
    _bind(ped.GetPrim(), m_base)
    _translate(ped.GetPrim(), 0, LINK_0_HEIGHT / 2.0, 0)

    j0 = UsdGeom.Xform.Define(stage, f"{root}/J0")
    _translate(j0.GetPrim(), 0, LINK_0_HEIGHT, 0)
    _add_ball(stage, f"{root}/J0/Ball", BALL_RADIUS_BASE, m_joint)

    UsdGeom.Xform.Define(stage, f"{root}/J0/J1")
    s1 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/Stick1")
    _translate(s1.GetPrim(), 0, LINK_1_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/Stick1/Geo", LINK_1_LENGTH, m_link)
    b1 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/BallXf")
    _translate(b1.GetPrim(), 0, LINK_1_LENGTH, 0)
    _add_ball(stage, f"{root}/J0/J1/BallXf/Ball", BALL_RADIUS_J1, m_joint)

    j2 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2")
    _translate(j2.GetPrim(), 0, LINK_1_LENGTH, 0)
    s2 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/Stick2")
    _translate(s2.GetPrim(), 0, LINK_2_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/J2/Stick2/Geo", LINK_2_LENGTH, m_link)
    b2 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/BallXf")
    _translate(b2.GetPrim(), 0, LINK_2_LENGTH, 0)
    _add_ball(stage, f"{root}/J0/J1/J2/BallXf/Ball", BALL_RADIUS_J2, m_joint)

    j3 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3")
    _translate(j3.GetPrim(), 0, LINK_2_LENGTH, 0)
    s3 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/Stick3")
    _translate(s3.GetPrim(), 0, LINK_3_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/J2/J3/Stick3/Geo", LINK_3_LENGTH, m_link)
    b3 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/BallXf")
    _translate(b3.GetPrim(), 0, LINK_3_LENGTH, 0)
    _add_ball(stage, f"{root}/J0/J1/J2/J3/BallXf/Ball", BALL_RADIUS_J3, m_joint)

    j4 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4")
    _translate(j4.GetPrim(), 0, LINK_3_LENGTH, 0)
    s4 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/Stick4")
    _translate(s4.GetPrim(), 0, LINK_4_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/J2/J3/J4/Stick4/Geo", LINK_4_LENGTH, m_link)
    b4 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/BallXf")
    _translate(b4.GetPrim(), 0, LINK_4_LENGTH, 0)
    _add_ball(stage, f"{root}/J0/J1/J2/J3/J4/BallXf/Ball", BALL_RADIUS_J4, m_joint)

    j5 = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/J5")
    _translate(j5.GetPrim(), 0, LINK_4_LENGTH, 0)
    _add_ball(stage, f"{root}/J0/J1/J2/J3/J4/J5/Ball", BALL_RADIUS_GRIPPER, m_joint)

    fl = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerL")
    _translate(fl.GetPrim(), -GRIPPER_SPREAD, 0, 0)
    fls = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerL/Stick")
    _translate(fls.GetPrim(), 0, GRIPPER_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerL/Stick/Geo", GRIPPER_LENGTH, m_gripper)

    fr = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerR")
    _translate(fr.GetPrim(), GRIPPER_SPREAD, 0, 0)
    frs = UsdGeom.Xform.Define(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerR/Stick")
    _translate(frs.GetPrim(), 0, GRIPPER_LENGTH / 2.0, 0)
    _add_stick(stage, f"{root}/J0/J1/J2/J3/J4/J5/FingerR/Stick/Geo", GRIPPER_LENGTH, m_gripper)

    s = stage
    return {
        "j0":      s.GetPrimAtPath(f"{root}/J0"),
        "j1":      s.GetPrimAtPath(f"{root}/J0/J1"),
        "j2":      s.GetPrimAtPath(f"{root}/J0/J1/J2"),
        "j3":      s.GetPrimAtPath(f"{root}/J0/J1/J2/J3"),
        "j4":      s.GetPrimAtPath(f"{root}/J0/J1/J2/J3/J4"),
        "j5":      s.GetPrimAtPath(f"{root}/J0/J1/J2/J3/J4/J5"),
        "fingerL": s.GetPrimAtPath(f"{root}/J0/J1/J2/J3/J4/J5/FingerL"),
        "fingerR": s.GetPrimAtPath(f"{root}/J0/J1/J2/J3/J4/J5/FingerR"),
    }


# =============================================================================
# JOINT APPLICATOR (radians)
# =============================================================================
def _r2d(r):
    return math.degrees(r)


def apply_joint_angles(prims, angles):
    rot = UsdGeom.XformCommonAPI.RotationOrderXYZ
    UsdGeom.XformCommonAPI(prims["j0"]).SetRotate(Gf.Vec3f(0, _r2d(angles.get("j0", 0.0)), 0), rot)
    UsdGeom.XformCommonAPI(prims["j1"]).SetRotate(Gf.Vec3f(0, 0, _r2d(angles.get("j1", 0.0))), rot)
    UsdGeom.XformCommonAPI(prims["j2"]).SetRotate(Gf.Vec3f(0, 0, _r2d(angles.get("j2", 0.0))), rot)
    UsdGeom.XformCommonAPI(prims["j3"]).SetRotate(Gf.Vec3f(0, 0, _r2d(angles.get("j3", 0.0))), rot)
    UsdGeom.XformCommonAPI(prims["j4"]).SetRotate(Gf.Vec3f(_r2d(angles.get("j4", 0.0)), 0, 0), rot)
    j5 = _r2d(angles.get("j5", 0.0))
    UsdGeom.XformCommonAPI(prims["fingerL"]).SetRotate(Gf.Vec3f(0, 0, -j5), rot)
    UsdGeom.XformCommonAPI(prims["fingerR"]).SetRotate(Gf.Vec3f(0, 0,  j5), rot)


# =============================================================================
# EXTENSION
# =============================================================================
class RobotArmExt(omni.ext.IExt):
    def on_startup(self, _ext_id):
        stage = _get_or_create_stage()
        self._prims   = build_robot(stage)
        self._objects = build_scene_objects(stage)
        self._angles  = dict(DEFAULT_ANGLES)
        apply_joint_angles(self._prims, self._angles)

        self._zmq_ctx = zmq.Context()

        # command socket (PULL)
        self._sock_cmd = self._zmq_ctx.socket(zmq.PULL)
        self._sock_cmd.bind(f"tcp://0.0.0.0:{ZMQ_PORT_CMD}")
        self._sock_cmd.setsockopt(zmq.RCVTIMEO, 0)

        # state socket (PUB)
        self._sock_state = self._zmq_ctx.socket(zmq.PUB)
        self._sock_state.bind(f"tcp://0.0.0.0:{ZMQ_PORT_STATE}")

        self._accum = 0.0
        self._sub_tick = omni.kit.app.get_app() \
            .get_update_event_stream() \
            .create_subscription_to_pop(self._on_update)

        print(f"[RobotArm] cmd PULL :{ZMQ_PORT_CMD}  state PUB :{ZMQ_PORT_STATE}")
        print(f"[RobotArm] scene: target + {len(OBSTACLES)} obstacles built")

    def _on_update(self, ev):
        # 1) drain command socket, keep latest
        latest = None
        try:
            while True:
                latest = self._sock_cmd.recv_json(flags=zmq.NOBLOCK)
        except zmq.Again:
            pass

        if latest is not None:
            # Accept both wire formats:
            #  - contract shape  {"joints": [j0..j5], "frame_id": i}  (dispatcher)
            #  - legacy shape    {"j0": ..., "j5": ...}               (older callers)
            if "joints" in latest and isinstance(latest["joints"], list):
                arr = latest["joints"]
                for i, k in enumerate(("j0", "j1", "j2", "j3", "j4", "j5")):
                    if i < len(arr):
                        self._angles[k] = float(arr[i])
            else:
                for k in ("j0", "j1", "j2", "j3", "j4", "j5"):
                    if k in latest:
                        self._angles[k] = float(latest[k])
            apply_joint_angles(self._prims, self._angles)

        # 2) publish state at ~10 Hz
        dt = ev.payload.get("dt", 0.016) if hasattr(ev, "payload") else 0.016
        self._accum += dt
        if self._accum >= STATE_PERIOD:
            self._accum = 0.0
            self._publish_state()

    def _publish_state(self):
        state = {
            "target":    TARGET_BALL,
            "obstacles": OBSTACLES,
            "angles":    self._angles,
        }
        try:
            self._sock_state.send_json(state, flags=zmq.NOBLOCK)
        except zmq.Again:
            pass

    def on_shutdown(self):
        if getattr(self, "_sub_tick", None):
            self._sub_tick.unsubscribe()
            self._sub_tick = None
        for s in ("_sock_cmd", "_sock_state"):
            sock = getattr(self, s, None)
            if sock is not None:
                sock.close()
                setattr(self, s, None)
        if getattr(self, "_zmq_ctx", None):
            self._zmq_ctx.term()
            self._zmq_ctx = None
        print("[RobotArm] shutdown - sockets closed")