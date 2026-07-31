import math
import csv
import os
import omni.ext
import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdShade, Usd

# =============================================================================
# CSV DATA STORE
# =============================================================================
CSV_PATH      = "/media/RBB2013/directory/kit-app-template/source/extensions/digitaltwin.satellite_extension/data/data.csv"
UPDATE_PERIOD = 0.5    # seconds per data row
POS_SCALE     = 40.0   # multiply pos_x/pos_y so motion is clearly visible

# =============================================================================
# SATELLITE GEOMETRY (cm, Y-up)
# GPS/navigation-style: hexagonal bus + two solar wings + antennas
# =============================================================================
BUS_RADIUS       = 20.0   # hex bus circumscribed radius
BUS_HEIGHT       = 25.0

# Solar wing = boom + N panels
WING_BOOM_LEN    = 15.0
WING_BOOM_RADIUS = 1.2
PANEL_LEN        = 40.0   # along boom (X)
PANEL_WIDTH      = 18.0   # spanwise (Z)
PANEL_THICK      = 0.6
PANELS_PER_WING  = 2

# Antennas (nadir side, -Y)
HELIX_COUNT      = 4       # L-band navigation helices
HELIX_RADIUS     = 1.6
HELIX_HEIGHT     = 10.0
HELIX_RING_R     = 10.0    # radius on which helices sit
HGA_DISH_RADIUS  = 6.0     # high-gain dish
HGA_DEPTH        = 2.0
HGA_BOOM_LEN     = 6.0

# Zenith (+Y) omni whip
WHIP_LEN         = 12.0
WHIP_RADIUS      = 0.4

# =============================================================================
# ORBIT
# =============================================================================
ORBIT_RADIUS     = 250.0
ORBIT_PERIOD_S   = 20.0    # full revolution
SPIN_PERIOD_S    =  8.0    # bus yaw about Y
PANEL_TRACK_HZ   =  0.05   # slow sun-track rotation of panels

# =============================================================================
# COLOURS
# =============================================================================
MAT_BUS_COLOR    = Gf.Vec3f(0.82, 0.78, 0.55)   # gold MLI foil
MAT_PANEL_COLOR  = Gf.Vec3f(0.05, 0.10, 0.35)   # dark blue solar cells
MAT_BOOM_COLOR   = Gf.Vec3f(0.70, 0.70, 0.72)
MAT_ANT_COLOR    = Gf.Vec3f(0.90, 0.90, 0.92)
MAT_DISH_COLOR   = Gf.Vec3f(0.85, 0.85, 0.88)
MAT_WHIP_COLOR   = Gf.Vec3f(0.20, 0.20, 0.22)


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


def _rotate(prim, rx, ry, rz):
    UsdGeom.XformCommonAPI(prim).SetRotate(
        Gf.Vec3f(rx, ry, rz), UsdGeom.XformCommonAPI.RotationOrderXYZ
    )


def _scale(prim, sx, sy, sz):
    UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(sx, sy, sz))


def _hex_prism(stage, path, radius, height, mat):
    """Hexagonal prism built as a Mesh."""
    m = UsdGeom.Mesh.Define(stage, path)
    hy = height / 2.0
    pts = []
    for i in range(6):
        a = math.pi / 3.0 * i
        x, z = radius * math.cos(a), radius * math.sin(a)
        pts.append(Gf.Vec3f(x, -hy, z))
    for i in range(6):
        a = math.pi / 3.0 * i
        x, z = radius * math.cos(a), radius * math.sin(a)
        pts.append(Gf.Vec3f(x,  hy, z))

    face_vertex_counts = [6, 6] + [4] * 6
    face_vertex_indices = [5, 4, 3, 2, 1, 0,          # bottom (reversed for outward normal)
                           6, 7, 8, 9, 10, 11]        # top
    for i in range(6):
        j = (i + 1) % 6
        face_vertex_indices += [i, j, j + 6, i + 6]   # side quad

    m.CreatePointsAttr(pts)
    m.CreateFaceVertexCountsAttr(face_vertex_counts)
    m.CreateFaceVertexIndicesAttr(face_vertex_indices)
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    _bind(m.GetPrim(), mat)
    return m.GetPrim()


def _cyl(stage, path, radius, height, axis, mat):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.CreateRadiusAttr(radius)
    c.CreateHeightAttr(height)
    c.CreateAxisAttr(axis)
    _bind(c.GetPrim(), mat)
    return c.GetPrim()


def _panel(stage, path, length, width, thick, mat):
    """Thin box panel using scaled cube."""
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(1.0)
    _bind(c.GetPrim(), mat)
    _scale(c.GetPrim(), length, thick, width)
    return c.GetPrim()


def _dish(stage, path, radius, depth, mat):
    """Shallow dish faked with a scaled sphere clipped by scaling."""
    sp = UsdGeom.Sphere.Define(stage, path)
    sp.CreateRadiusAttr(radius)
    _bind(sp.GetPrim(), mat)
    # Flatten in Y to look like a dish
    _scale(sp.GetPrim(), 1.0, depth / radius, 1.0)
    return sp.GetPrim()


# =============================================================================
# SCENE BUILD
# =============================================================================
def build_satellite(stage):
    root = "/World/Satellite"
    orbit = UsdGeom.Xform.Define(stage, root)                     # orbit anchor
    _translate(orbit.GetPrim(), ORBIT_RADIUS, 0, 0)

    body = UsdGeom.Xform.Define(stage, f"{root}/Body")            # spinning bus + payload
    body_prim = body.GetPrim()

    mp = f"{root}/Body/Materials"
    m_bus   = _make_material(stage, f"{mp}/Bus",   MAT_BUS_COLOR,   0.35, 0.60)
    m_panel = _make_material(stage, f"{mp}/Panel", MAT_PANEL_COLOR, 0.20, 0.10)
    m_boom  = _make_material(stage, f"{mp}/Boom",  MAT_BOOM_COLOR,  0.55, 0.30)
    m_ant   = _make_material(stage, f"{mp}/Ant",   MAT_ANT_COLOR,   0.30, 0.70)
    m_dish  = _make_material(stage, f"{mp}/Dish",  MAT_DISH_COLOR,  0.25, 0.50)
    m_whip  = _make_material(stage, f"{mp}/Whip",  MAT_WHIP_COLOR,  0.60, 0.20)

    # --- Hexagonal bus ---
    _hex_prism(stage, f"{root}/Body/Bus", BUS_RADIUS, BUS_HEIGHT, m_bus)

    # --- Solar wings (+X and -X) ---
    panel_pivots = []
    for side, sign in (("WingP", +1.0), ("WingN", -1.0)):
        wing = UsdGeom.Xform.Define(stage, f"{root}/Body/{side}")
        # boom out along X
        boom = UsdGeom.Xform.Define(stage, f"{root}/Body/{side}/Boom")
        _translate(boom.GetPrim(), sign * (BUS_RADIUS + WING_BOOM_LEN / 2.0), 0, 0)
        _rotate(boom.GetPrim(), 0, 0, 90)  # cylinder default Y axis -> lay along X
        _cyl(stage, f"{root}/Body/{side}/Boom/Geo",
             WING_BOOM_RADIUS, WING_BOOM_LEN, UsdGeom.Tokens.y, m_boom)

        # panel pivot at boom tip -> allows sun-tracking rotation about X
        pivot = UsdGeom.Xform.Define(stage, f"{root}/Body/{side}/PanelPivot")
        pivot_x = sign * (BUS_RADIUS + WING_BOOM_LEN)
        _translate(pivot.GetPrim(), pivot_x, 0, 0)
        panel_pivots.append(pivot.GetPrim())

        # N panels extending outboard along X
        for i in range(PANELS_PER_WING):
            px = sign * (PANEL_LEN / 2.0 + i * PANEL_LEN)
            p = UsdGeom.Xform.Define(stage, f"{root}/Body/{side}/PanelPivot/Panel{i}")
            _translate(p.GetPrim(), px, 0, 0)
            _panel(stage, f"{root}/Body/{side}/PanelPivot/Panel{i}/Geo",
                   PANEL_LEN * 0.98, PANEL_WIDTH, PANEL_THICK, m_panel)

    # --- Nadir antenna farm (-Y side) ---
    nadir_y = -BUS_HEIGHT / 2.0
    for i in range(HELIX_COUNT):
        a = 2.0 * math.pi * i / HELIX_COUNT
        hx = HELIX_RING_R * math.cos(a)
        hz = HELIX_RING_R * math.sin(a)
        helix = UsdGeom.Xform.Define(stage, f"{root}/Body/Helix{i}")
        _translate(helix.GetPrim(), hx, nadir_y - HELIX_HEIGHT / 2.0, hz)
        _cyl(stage, f"{root}/Body/Helix{i}/Geo",
             HELIX_RADIUS, HELIX_HEIGHT, UsdGeom.Tokens.y, m_ant)

    # --- High-gain dish on short boom (-Y, offset) ---
    hga = UsdGeom.Xform.Define(stage, f"{root}/Body/HGA")
    _translate(hga.GetPrim(), 0, nadir_y - HGA_BOOM_LEN, 0)
    _cyl(stage, f"{root}/Body/HGA/Boom",
         WING_BOOM_RADIUS, HGA_BOOM_LEN, UsdGeom.Tokens.y, m_boom)
    dish_xf = UsdGeom.Xform.Define(stage, f"{root}/Body/HGA/Dish")
    _translate(dish_xf.GetPrim(), 0, -HGA_BOOM_LEN / 2.0 - HGA_DEPTH, 0)
    _dish(stage, f"{root}/Body/HGA/Dish/Geo", HGA_DISH_RADIUS, HGA_DEPTH, m_dish)

    # --- Zenith omni whip (+Y) ---
    whip = UsdGeom.Xform.Define(stage, f"{root}/Body/Whip")
    _translate(whip.GetPrim(), 0, BUS_HEIGHT / 2.0 + WHIP_LEN / 2.0, 0)
    _cyl(stage, f"{root}/Body/Whip/Geo",
         WHIP_RADIUS, WHIP_LEN, UsdGeom.Tokens.y, m_whip)

    return {
        "orbit":  orbit.GetPrim(),
        "body":   body_prim,
        "panels": panel_pivots,
    }


# =============================================================================
# CSV LOADER
# =============================================================================
def load_csv_rows(path):
    if not os.path.isfile(path):
        print(f"[Satellite] CSV not found: {path}")
        return []
    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append({
                    "time":        float(r["time"]),
                    "pos_x":       float(r["pos_x"]),
                    "pos_y":       float(r["pos_y"]),
                    "yaw":         float(r["yaw"]),
                    "temperature": float(r["temperature"]),
                    "vibration":   float(r["vibration"]),
                })
            except (KeyError, ValueError) as e:
                print(f"[Satellite] skipping bad CSV row {r}: {e}")
    print(f"[Satellite] loaded {len(rows)} rows from {path}")
    return rows


def _shortest_angle_lerp(a, b, t):
    """Interpolate degrees a -> b along the shortest arc."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * t


# =============================================================================
# POSE FROM CSV (with smooth interpolation between rows)
# =============================================================================
def apply_pose_from_rows(handles, cur, nxt, alpha):
    x = (cur["pos_x"] + (nxt["pos_x"] - cur["pos_x"]) * alpha) * POS_SCALE
    y = (cur["pos_y"] + (nxt["pos_y"] - cur["pos_y"]) * alpha) * POS_SCALE
    yaw = _shortest_angle_lerp(cur["yaw"], nxt["yaw"], alpha)

    orbit_prim = handles["orbit"]
    UsdGeom.XformCommonAPI(orbit_prim).SetTranslate(Gf.Vec3d(x, y, 0.0))
    _rotate(handles["body"], 0.0, yaw, 0.0)


# =============================================================================
# EXTENSION
# =============================================================================
class SatelliteExt(omni.ext.IExt):
    def on_startup(self, _ext_id):
        stage = _get_or_create_stage()
        self._handles = build_satellite(stage)

        self._rows = load_csv_rows(CSV_PATH)
        self._idx = 0
        self._accum = 0.0
        if self._rows:
            cur = self._rows[0]
            nxt = self._rows[1 % len(self._rows)]
            apply_pose_from_rows(self._handles, cur, nxt, 0.0)
            print(f"[Satellite] row 0 -> pos_x={cur['pos_x']:.3f} "
                  f"pos_y={cur['pos_y']:.3f} yaw={cur['yaw']:.1f}")

        self._sub_tick = omni.kit.app.get_app() \
            .get_update_event_stream() \
            .create_subscription_to_pop(self._on_update)

        print(f"[Satellite] GPS-style satellite built, "
              f"driven by CSV ({len(self._rows)} rows, {UPDATE_PERIOD}s/row)")

    def _on_update(self, ev):
        if not self._rows:
            return
        dt = ev.payload.get("dt", 0.016) if hasattr(ev, "payload") else 0.016
        self._accum += dt

        while self._accum >= UPDATE_PERIOD:
            self._accum -= UPDATE_PERIOD
            self._idx = (self._idx + 1) % len(self._rows)
            r = self._rows[self._idx]
            print(f"[Satellite] row {self._idx} -> pos_x={r['pos_x']:.3f} "
                  f"pos_y={r['pos_y']:.3f} yaw={r['yaw']:.1f} "
                  f"temp={r['temperature']:.2f} vib={r['vibration']:.3f}")

        alpha = self._accum / UPDATE_PERIOD
        cur = self._rows[self._idx]
        nxt = self._rows[(self._idx + 1) % len(self._rows)]
        apply_pose_from_rows(self._handles, cur, nxt, alpha)

    def on_shutdown(self):
        if getattr(self, "_sub_tick", None):
            self._sub_tick.unsubscribe()
            self._sub_tick = None
        print("[Satellite] shutdown")
