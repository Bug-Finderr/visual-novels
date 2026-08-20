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
    # How many story generations may run at once. Beyond this they QUEUE.
    # Sizing: a pipeline peaks near 500MB resident against a 2GB Render
    # Standard instance with a ~130MB baseline, so 3 leaves real headroom and
    # 4-5 is the hard ceiling. Raise it only with the RAM to back it — an OOM
    # kills every in-flight generation and the web service with it.
    MAX_CONCURRENT_GENERATIONS: int = 3
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

    # --- Asset storage: local disk (dev) or a public GCS bucket (prod) ---
    ASSET_BACKEND: str = "local"          # 'local' | 'gcs'
    GCS_BUCKET: str | None = None         # bucket name when ASSET_BACKEND=gcs
    # Public/CDN base for reading assets from the browser. Defaults to the
    # bucket's public endpoint; set to a Cloud CDN / custom domain in prod.
    GCS_PUBLIC_BASE: str | None = None
    # Session-cookie flags. Flip Secure on behind HTTPS; SameSite must be
    # 'none' (with Secure) only if the SPA is served from a different site
    # than the API — a same-origin proxy keeps it 'lax'.
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"  # 'lax' | 'strict' | 'none'

    # --- Billing: prepaid credits + Cashfree (INR) ----------------------
    # Master switch. OFF by default so the schema, routes and UI can ship
    # (and be tested) without paywalling the live site while Cashfree KYC is
    # pending — when False, /generate skips the debit entirely.
    BILLING_ENABLED: bool = False
    # Credits granted once, on first read of a user's credit account. Lazy
    # rather than at signup so existing accounts get backfilled too.
    FREE_STORY_CREDITS: int = 2
    # Credits burned per story generation (and per chapter continuation).
    CREDITS_PER_GENERATION: int = 1
    # Refund the credit when the generation pipeline errors out. Off by
    # default (each attempt is charged); flip on during a Gemini outage
    # rather than shipping a code change.
    REFUND_ON_GENERATION_FAILURE: bool = False

    CASHFREE_ENV: str = "sandbox"          # 'sandbox' | 'production'
    CASHFREE_APP_ID: str | None = None
    CASHFREE_SECRET_KEY: str | None = None
    # Webhook signatures are signed with the secret key; split only if
    # Cashfree ever issues a distinct webhook secret.
    CASHFREE_WEBHOOK_SECRET: str | None = None
    CASHFREE_API_VERSION: str = "2026-01-01"
    CASHFREE_TIMEOUT: float = 30
    # Where the SPA lives — used to build the post-checkout return URL.
    # Defaults to the first CORS origin, which is already the frontend.
    PUBLIC_WEB_BASE: str | None = None
    # Public origin of THIS API, for the Cashfree webhook (notify_url).
    PUBLIC_API_BASE: str | None = None

    models: Models = Models()

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return tuple(o.strip() for o in v.split(",") if o.strip())
        return tuple(v)

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _force_psycopg_driver(cls, v: str) -> str:
        # Managed Postgres providers (Render, Heroku, Supabase, Neon, ...) hand
        # out a plain postgres:// / postgresql:// URL; SQLAlchemy needs the
        # +psycopg driver suffix. Rewrite rather than requiring every deploy
        # target to hand-edit the connection string.
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @field_validator(
        "STORYGEN_ENGINE", "ASSET_BACKEND", "SESSION_COOKIE_SAMESITE", "CASHFREE_ENV",
        mode="after",
    )
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

    @property
    def cashfree_configured(self) -> bool:
        return bool(self.CASHFREE_APP_ID and self.CASHFREE_SECRET_KEY)

    @property
    def cashfree_webhook_secret(self) -> str | None:
        return self.CASHFREE_WEBHOOK_SECRET or self.CASHFREE_SECRET_KEY

    @property
    def web_base(self) -> str:
        """Origin of the SPA — the post-checkout return URL is built off this."""
        if self.PUBLIC_WEB_BASE:
            return self.PUBLIC_WEB_BASE.rstrip("/")
        return (self.ALLOWED_ORIGINS[0] if self.ALLOWED_ORIGINS else "http://localhost:3000").rstrip("/")


config = Config()
