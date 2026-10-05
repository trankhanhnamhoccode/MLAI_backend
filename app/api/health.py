from fastapi import APIRouter, Request

from app.schemas.health import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(request: Request) -> HealthResponse:
    return HealthResponse(status="ok", service=request.app.state.settings.app_name)
