import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

_SERVER_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SERVER_DIR.parent

load_dotenv(_ROOT_DIR / ".env")


def _int_env(key: str, default: int) -> int:
    """int() from env, tolerant of malformed values (don't crash app import)."""
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(key: str, default: bool = False) -> bool:
    return os.getenv(key, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Models:
    story_pro: str = "gemini-2.5-pro"
    dialogue_flash: str = "gemini-2.5-flash"
    image_gen: str = "gemini-2.5-flash-image"


@dataclass(frozen=True)
class Config:
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    PORT: int = int(os.getenv("PORT_SERVER", "3001"))
    DATA_DIR: Path = _SERVER_DIR / "data"
    DB_PATH: Path = _SERVER_DIR / "data" / "storyplex.db"
    GENERATED_DIR: Path = _SERVER_DIR / "data" / "generated"
    PUPPETEER_URL: str | None = os.getenv("PUPPETEER_URL")  # e.g. http://localhost:8000
    PUPPETEER_TIMEOUT: float = float(os.getenv("PUPPETEER_TIMEOUT", "60"))
    TTS_URL: str | None = os.getenv("TTS_URL")  # e.g. http://34.182.211.49:8001
    TTS_TIMEOUT: float = float(os.getenv("TTS_TIMEOUT", "120"))
    # Silk / Mulberry TTS (rumik.ai). When SILK_API_KEY is set, this is the
    # active TTS backend (English, expressive, streaming) instead of Irodori.
    SILK_API_KEY: str | None = os.getenv("SILK_API_KEY")
    SILK_API_URL: str = os.getenv("SILK_API_URL", "https://silk-api.rumik.ai")
    SILK_MODEL: str = os.getenv("SILK_MODEL", "mulberry")
    SILK_TIMEOUT: float = float(os.getenv("SILK_TIMEOUT", "60"))
    # Story generation engine: "monolith" = single Gemini Pro call (default,
    # legacy); "graph" = LangGraph multi-agent pipeline (plot/world/character/
    # chapter agents + Memory gate). When "graph", the runtime Beat-Rewrite
    # Agent also handles custom free-text input.
    STORYGEN_ENGINE: str = os.getenv("STORYGEN_ENGINE", "monolith").strip().lower()
    # Max Memory-gate revision loops before the graph accepts best-effort.
    STORYGRAPH_MAX_REVISIONS: int = max(0, _int_env("STORYGRAPH_MAX_REVISIONS", 2))
    # Optional LLM semantic critic in the Memory gate (structural checks always
    # run). Off by default to keep generation deterministic and fast.
    STORYGRAPH_LLM_CRITIC: bool = _bool_env("STORYGRAPH_LLM_CRITIC", False)

    # --- Phase 1: persistence + accounts / auth -------------------------
    # Postgres for multi-user. Defaults to the local docker-compose DB.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://storyplex:storyplex@localhost:5432/storyplex",
    )
    # Google OAuth (owner-provided). Login is disabled until these are set.
    GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:3001/api/v1/auth/google/callback",
    )
    # Secret for signing the opaque server-session cookie. MUST be overridden
    # in production.
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "dev-insecure-change-me")
    SESSION_COOKIE: str = os.getenv("SESSION_COOKIE", "storyplex_session")
    SESSION_TTL_DAYS: int = _int_env("SESSION_TTL_DAYS", 30)
    # Credentialed-CORS allowlist (comma-separated). Where the SPA is served.
    ALLOWED_ORIGINS: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
    )

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    models: Models = field(default_factory=Models)


config = Config()
