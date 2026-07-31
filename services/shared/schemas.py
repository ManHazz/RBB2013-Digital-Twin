# CONTRACT — do not edit without Aiman's approval. Version: 1.0
from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    text: str


class TargetPose(BaseModel):
    x: float
    y: float
    z: float


class PlanRequest(BaseModel):
    target: TargetPose


class PlanResponse(BaseModel):
    joints: list[float] = Field(min_length=6, max_length=6)
    reachable: bool
    collision_free: bool


class DispatchRequest(BaseModel):
    joints: list[float] = Field(min_length=6, max_length=6)


class DispatchResponse(BaseModel):
    accepted: bool


class SimState(BaseModel):
    joints: list[float] = Field(min_length=6, max_length=6)
    ee_pose: TargetPose
    ts: float


class ActuationCommand(BaseModel):
    joints: list[float] = Field(min_length=6, max_length=6)
