from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bootstrap import bootstrap
from app.config import get_settings
from app.logging_utils import configure_logging
from app.scheduler import start_scheduler, stop_scheduler
from app.web.routes import router
from app.web.xhs_routes import router as xhs_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap()
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    static_dir = Path(__file__).resolve().parent / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    application.include_router(router)
    application.include_router(xhs_router)
    return application


app = create_app()
