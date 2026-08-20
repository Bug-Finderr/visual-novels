"""Application entry point.

`create_app()` is the composition root: it wires middleware, routers, and
error handlers into a fresh FastAPI instance. Keeping it a factory (rather than
building the app at import time) makes the app trivially testable — a test can
spin up an isolated instance — and keeps `main.py` a thin assembly layer over
the feature routers. The module-level `app` is what `uvicorn app.main:app`
serves.

Every HTTP surface lives under `/api/v1`; the routers own their sub-prefixes.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth.router import router as auth_router
from app.config import config
from app.db.database import init_database
from app.logger import logger
from app.routes import (
    assets, billing, gameplay, generation, library, saves, sessions, social, tts_stream,
)

API_PREFIX = "/api/v1"

# Every feature router, in include order. Each is already prefixed under
# /api/v1 by its own APIRouter(prefix=...); listing them here keeps the
# composition root declarative.
_ROUTERS = (
    auth_router,
    billing.router,
    library.router,
    social.router,
    sessions.router,
    generation.router,
    gameplay.router,
    assets.router,
    tts_stream.router,
    saves.router,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


def _install_middleware(application: FastAPI) -> None:
    # Credentialed CORS against an explicit allowlist (required for cookie auth).
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Needed by Authlib to hold the OAuth state/nonce between login and callback.
    application.add_middleware(
        SessionMiddleware,
        secret_key=config.SESSION_SECRET,
        same_site="lax",
        https_only=config.SESSION_COOKIE_SECURE,  # True behind HTTPS in prod
    )


def _install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_, exc: StarletteHTTPException):
        # Map FastAPI's {"detail": "..."} to the original {"error": "..."} contract.
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(_, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"error": str(exc) or "Internal server error"})


def create_app() -> FastAPI:
    """Build and return a fully-wired FastAPI application."""
    application = FastAPI(title="storyplex-server", lifespan=lifespan)
    _install_middleware(application)
    for router in _ROUTERS:
        application.include_router(router)

    @application.get(f"{API_PREFIX}/health")
    def health():
        return {"status": "ok", "name": "storyplex-server"}

    _install_error_handlers(application)
    return application


app = create_app()


def main() -> None:  # entry point for `python -m app.main`
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=True)


if __name__ == "__main__":
    main()
