from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    application = FastAPI(
        title=configuration.app_name,
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    application.state.settings = configuration
    application.include_router(health_router)
    return application


app = create_app()
