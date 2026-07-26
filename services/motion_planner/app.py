from fastapi import FastAPI
from services.shared.schemas import PlanRequest, PlanResponse

app = FastAPI()

@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    return PlanResponse(joints=[0.0]*6, reachable=True, collision_free=True)
