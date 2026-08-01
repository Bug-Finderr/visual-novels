"""Typed application settings, backed by pydantic-settings.

Values resolve in priority order: constructor args → environment variables →
the repo-root `.env` → the defaults declared here. `load_dotenv` still runs so
that modules reading `os.getenv` directly (e.g. the logger's LOG_LEVEL) keep
seeing `.env` values — pydantic-settings only injects into this object.

The public surface is unchanged from the old dataclass: `from app.config import
config`, every UPPER_CASE attribute, the nested `config.models`, and the
`config.google_oauth_enabled` property.
"""
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_SERVER_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SERVER_DIR.parent

# Populate os.environ so direct readers (logger LOG_LEVEL, etc.) see .env too.
load_dotenv(_ROOT_DIR / ".env")


class Models(BaseModel):
    story_pro: str = "gemini-2.5-pro"
    dialogue_flash: str = "gemini-2.5-flash"
    image_gen: str = "gemini-2.5-flash-image"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    GEMINI_API_KEY: str | None = None
    PORT: int = Field(default=3001, validation_alias="PORT_SERVER")
    # Fixed data locations (still env-overridable, but not normally configured).
    DATA_DIR: Path = _SERVER_DIR / "data"
    DB_PATH: Path = _SERVER_DIR / "data" / "storyplex.db"
    GENERATED_DIR: Path = _SERVER_DIR / "data" / "generated"

    PUPPETEER_URL: str | None = None  # e.g. http://localhost:8000
    PUPPETEER_TIMEOUT: float = 60
    TTS_URL: str | None = None  # e.g. http://34.182.211.49:8001
    TTS_TIMEOUT: float = 120

    # Silk / Mulberry TTS (rumik.ai). When SILK_API_KEY is set, this is the
    # active TTS backend (English, expressive, streaming) instead of Irodori.
    SILK_API_KEY: str | None = None
    SILK_API_URL: str = "https://silk-api.rumik.ai"
    SILK_MODEL: str = "mulberry"
    SILK_TIMEOUT: float = 60

    # Story generation engine: "monolith" = single Gemini Pro call (default,
    # legacy); "graph" = LangGraph multi-agent pipeline (plot/world/character/
    # chapter agents + Memory gate). When "graph", the runtime Beat-Rewrite
    # Agent also handles custom free-text input.
    STORYGEN_ENGINE: str = "monolith"
    # Max Memory-gate revision loops before the graph accepts best-effort.
    STORYGRAPH_MAX_REVISIONS: int = 2
    # Optional LLM semantic critic in the Memory gate (structural checks always
    # run). Off by default to keep generation deterministic and fast.
    STORYGRAPH_LLM_CRITIC: bool = False

    # --- Persistence + accounts / auth ---------------------------------
    # Postgres for multi-user. Defaults to the local docker-compose DB.
    DATABASE_URL: str = "postgresql+psycopg://storyplex:storyplex@localhost:5432/storyplex"
    # Google OAuth (owner-provided). Login is disabled until these are set.
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:3001/api/v1/auth/google/callback"
    # Secret for signing the opaque server-session cookie. MUST be overridden
    # in production.
    SESSION_SECRET: str = "dev-insecure-change-me"
    SESSION_COOKIE: str = "storyplex_session"
    SESSION_TTL_DAYS: int = 30
    # Credentialed-CORS allowlist (comma-separated). Where the SPA is served.
    # NoDecode keeps pydantic from JSON-parsing the raw env string so the
    # validator below can split it on commas.
    ALLOWED_ORIGINS: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:3000",)

    models: Models = Models()

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return tuple(o.strip() for o in v.split(",") if o.strip())
        return tuple(v)

    @field_validator("STORYGEN_ENGINE", mode="after")
    @classmethod
    def _normalize_engine(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("STORYGRAPH_MAX_REVISIONS", mode="before")
    @classmethod
    def _clamp_revisions(cls, v) -> int:
        # Tolerate a malformed env value (fall back to 2) rather than crashing
        # app import — matches the old _int_env behaviour.
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return 2

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


config = Config()
