from fastapi import FastAPI

from services.shared.schemas import (
    DispatchRequest,
    DispatchResponse,
)

app = FastAPI(
    title="Dispatcher Service",
    version="1.0"
)


@app.post("/dispatch", response_model=DispatchResponse)
def dispatch(request: DispatchRequest):
    """
    Accept a robot joint command.

    Task Ibrohim-01:
    Only acknowledge the request.
    Interpolation will be added in Ibrohim-02.
    """
    return DispatchResponse(accepted=True)