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
from app.routes import assets, gameplay, generation, library, saves, sessions, social, tts_stream


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="storyplex-server", lifespan=lifespan)

# Credentialed CORS against an explicit allowlist (required for cookie auth).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Needed by Authlib to hold the OAuth state/nonce between login and callback.
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    same_site="lax",
    https_only=False,  # dev is http://localhost
)

app.include_router(auth_router)
app.include_router(library.router)
app.include_router(social.router)
app.include_router(sessions.router)
app.include_router(generation.router)
app.include_router(gameplay.router)
app.include_router(assets.router)
app.include_router(tts_stream.router)
app.include_router(saves.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "name": "storyplex-server"}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_, exc: StarletteHTTPException):
    # Map FastAPI's {"detail": "..."} to the original {"error": "..."} contract
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": str(exc) or "Internal server error"})


def main() -> None:  # entry point for `python -m app.main`
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=True)


if __name__ == "__main__":
    main()
