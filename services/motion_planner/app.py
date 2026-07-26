from fastapi import FastAPI
from services.shared.schemas import PlanRequest, PlanResponse
from services.motion_planner import robot_ik as ik

app = FastAPI()


@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    x, y, z = req.target.x, req.target.y, req.target.z

    if not ik.reachable(x, y, z):
        return PlanResponse(joints=[0.0] * 6, reachable=False, collision_free=True)

    angles = ik.solve(x, y, z)
    joints = [angles["j0"], angles["j1"], angles["j2"], angles["j3"], angles["j4"], 0.0]

    collision_free = not ik.collides(angles, obstacles=[])
    return PlanResponse(joints=joints, reachable=True, collision_free=collision_free)