"""SQLAlchemy models — the full target Postgres schema.

Existing tables mirror the legacy sqlite schema exactly (so the query layer can
be cut over without behaviour changes); JSON payloads stay as Text because the
app json-dumps/loads them itself. New tables + columns add identity (users,
oauth, auth sessions), ownership/visibility on stories, and the per-user
Playthrough that splits play-state off the shared story row.
"""
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


# ======================================================================
# Identity
# ======================================================================
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=False, unique=True)
    display_name = Column(Text)
    avatar_url = Column(Text)
    bio = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_seen_at = Column(DateTime)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)          # 'google'
    provider_user_id = Column(String, nullable=False)  # Google 'sub'
    email = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),)


class AuthSession(Base):
    """Opaque server session — the random token is stored hashed; the raw value
    lives only in the user's Secure/HttpOnly cookie."""
    __tablename__ = "auth_sessions"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    user_agent = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ======================================================================
# Story (authored content + — for now — legacy play state)
# ======================================================================
class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    status = Column(String, nullable=False, server_default="created")
    setup_genre = Column(Text, nullable=False)
    setup_art_style = Column(Text, nullable=False)
    setup_setting = Column(Text, nullable=False)
    setup_protagonist_name = Column(Text, nullable=False)
    setup_protagonist_personality = Column(Text, nullable=False)
    setup_tone = Column(Text, nullable=False)
    setup_premise = Column(Text)
    world_lore = Column(Text)
    plot_arc = Column(Text)
    current_scene_id = Column(String)
    current_label = Column(String, server_default="Start")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_played_at = Column(DateTime)
    # spine model
    story_spine = Column(Text)
    endings = Column(Text)
    alignment_state = Column(Text, server_default="{}")
    current_beat_index = Column(Integer, server_default="0")
    chosen_ending_id = Column(String)
    # chapters
    parent_session_id = Column(String)
    chapter_number = Column(Integer, server_default="1")
    storygen_engine = Column(String, server_default="monolith")
    # --- Phase 1/3 additions: ownership + publishing + denormalized counts ---
    owner_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    visibility = Column(String, nullable=False, server_default="private")  # private|unlisted|public
    published_at = Column(DateTime)
    slug = Column(String, unique=True)
    like_count = Column(Integer, nullable=False, server_default="0")
    comment_count = Column(Integer, nullable=False, server_default="0")
    play_count = Column(Integer, nullable=False, server_default="0")
    rating_sum = Column(Integer, nullable=False, server_default="0")
    rating_count = Column(Integer, nullable=False, server_default="0")
    __table_args__ = (Index("idx_sessions_visibility_published", "visibility", "published_at"),)


class Character(Base):
    __tablename__ = "characters"
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True, index=True)
    name = Column(Text, nullable=False)
    color = Column(String, nullable=False, server_default="#FFFFFF")
    role = Column(Text)
    personality = Column(Text)
    appearance = Column(Text)
    backstory = Column(Text)
    relationship = Column(Text)
    speech_style = Column(Text)
    quirks = Column(Text)
    sprites_generated = Column(Integer, server_default="0")
    is_dynamic = Column(Integer, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    voice_caption = Column(Text)
    voice_id = Column(String)
    gender = Column(String)


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    narrative_context = Column(Text)
    image_generated = Column(Integer, server_default="0")
    is_dynamic = Column(Integer, server_default="0")
    created_at = Column(DateTime, server_default=func.now())


class ScriptLabel(Base):
    __tablename__ = "script_labels"
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True, index=True)
    label_name = Column(String, primary_key=True)
    statements = Column(Text, nullable=False)
    sort_order = Column(Integer, server_default="0")
    created_at = Column(DateTime, server_default=func.now())


class DialogueHistory(Base):
    __tablename__ = "dialogue_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    label_context = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (Index("idx_dialogue_history_session", "session_id", "created_at"),)


class BeatExpansion(Base):
    __tablename__ = "beat_expansions"
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    beat_index = Column(Integer, primary_key=True)
    source_choice_tag = Column(String, primary_key=True, server_default="")
    statements = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class EndingDialogue(Base):
    __tablename__ = "ending_dialogue"
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    ending_id = Column(String, primary_key=True)
    statements = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Save(Base):
    __tablename__ = "saves"
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))  # Phase 1: per-user saves
    slot = Column(Integer)
    name = Column(Text)
    current_label = Column(String, nullable=False)
    statement_index = Column(Integer, server_default="0")
    current_scene_id = Column(String)
    current_beat_index = Column(Integer, server_default="0")
    alignment_state = Column(Text)
    chosen_ending_id = Column(String)
    visible_characters = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (Index("idx_saves_session", "session_id", "created_at"),)


# ======================================================================
# Per-user play state (splits play progress off the shared story row)
# ======================================================================
class Playthrough(Base):
    __tablename__ = "playthroughs"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    current_label = Column(String, server_default="Start")
    statement_index = Column(Integer, server_default="0")
    current_scene_id = Column(String)
    current_beat_index = Column(Integer, server_default="0")
    alignment_state = Column(Text, server_default="{}")
    chosen_ending_id = Column(String)
    last_played_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "story_id", name="uq_playthrough_user_story"),)


# ======================================================================
# Social graph (Phase 4) — reactions on published stories.
# Denormalized counters live on sessions (like_count / rating_* / comment_count).
# ======================================================================
class Like(Base):
    __tablename__ = "likes"
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, server_default=func.now())


class Rating(Base):
    __tablename__ = "ratings"
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    score = Column(Integer, nullable=False)  # 1..5
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Comment(Base):
    __tablename__ = "comments"
    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_comment_id = Column(String, ForeignKey("comments.id", ondelete="CASCADE"))
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime)
    __table_args__ = (Index("idx_comments_session_created", "session_id", "created_at"),)


class Follow(Base):
    __tablename__ = "follows"
    follower_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    followee_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at = Column(DateTime, server_default=func.now())


# ======================================================================
# Billing — prepaid credits + Cashfree orders.
#
# One credit == one story generation (~Rs.110 of Gemini spend), debited at
# the /generate gate. `credit_accounts.balance` is authoritative and is only
# ever moved by a conditional UPDATE (`... WHERE balance >= n`), so a
# concurrent double-spend loses the race instead of going negative;
# `credit_ledger` is the append-only audit of every movement.
# ======================================================================
class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance = Column(Integer, nullable=False, server_default="0")
    lifetime_purchased = Column(Integer, nullable=False, server_default="0")
    # Free signup grant, recorded so it can only ever be handed out once —
    # even if the configured grant size changes later.
    free_granted = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delta = Column(Integer, nullable=False)          # +n granted/purchased/refunded, -n spent
    reason = Column(String, nullable=False)          # signup_grant|purchase|generation|refund|admin
    balance_after = Column(Integer, nullable=False)
    ref_type = Column(String)                        # 'order' | 'session'
    ref_id = Column(String)
    # Purchases set 'order:{order_id}' so a webhook replay (or a webhook
    # racing the return-url verify) can never credit twice. Spends leave it
    # NULL — Postgres UNIQUE ignores NULLs, and one session may legitimately
    # be charged more than once across retries.
    idempotency_key = Column(String, unique=True)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (Index("idx_credit_ledger_user_created", "user_id", "created_at"),)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    order_id = Column(String, primary_key=True)      # ours: 'sp_<uuid4hex>'
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_id = Column(String, nullable=False)
    # credits + price are SNAPSHOT at order time: repricing a pack must not
    # change what an in-flight order settles at.
    credits = Column(Integer, nullable=False)
    amount_paise = Column(Integer, nullable=False)   # paise, never float
    currency = Column(String, nullable=False, server_default="INR")
    # created|paid|failed|abandoned|expired|refunded|partially_refunded
    status = Column(String, nullable=False, server_default="created")
    customer_phone = Column(String)                  # Cashfree requires one per order
    cf_order_id = Column(String)
    payment_session_id = Column(Text)
    cf_payment_id = Column(String)
    credited_at = Column(DateTime)                   # non-null == credits granted
    raw_status_payload = Column(Text)
    # Why a payment didn't land, lifted out of the webhook's error_details so
    # "what is failing for our users" is a GROUP BY rather than hand-reading
    # JSON blobs. 'abandoned' (user dropped at OTP/UPI-PIN) is tracked apart
    # from 'failed' (bank declined) because they call for different fixes.
    failure_code = Column(String)
    failure_reason = Column(String)
    failure_description = Column(Text)
    last_event_type = Column(String)
    # Refund totals, maintained from REFUND_STATUS_WEBHOOK. Partial refunds
    # accumulate here; per-refund detail lives in `refunds`.
    refunded_paise = Column(Integer, nullable=False, server_default="0")
    credits_reclaimed = Column(Integer, nullable=False, server_default="0")
    refunded_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Refund(Base):
    """A refund against a paid order, learned from REFUND_STATUS_WEBHOOK.

    Refunds are initiated from the Cashfree dashboard, not from this app — but
    the credits they bought must come back, or a customer gets their money AND
    keeps the stories. One row per refund because an order can be refunded
    partially, more than once.
    """
    __tablename__ = "refunds"
    cf_refund_id = Column(String, primary_key=True)   # Cashfree's id; natural dedupe key
    order_id = Column(String, ForeignKey("payment_orders.order_id", ondelete="CASCADE"),
                      nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refund_id = Column(String)                        # merchant-side id, if set
    amount_paise = Column(Integer, nullable=False)
    status = Column(String, nullable=False)           # SUCCESS|PENDING|CANCELLED|ONHOLD
    refund_type = Column(String)                      # MERCHANT_INITIATED|PAYMENT_AUTO_REFUND
    status_description = Column(Text)
    # Credits taken back. Non-null == the clawback has been applied, which is
    # what keeps a repeated webhook from reclaiming twice.
    credits_reclaimed = Column(Integer)
    reclaimed_at = Column(DateTime)
    processed_at = Column(DateTime)
    raw_payload = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class WebhookEvent(Base):
    """Received Cashfree webhooks, kept for replay protection + forensics."""
    __tablename__ = "webhook_events"
    id = Column(String, primary_key=True, default=_uuid)
    signature = Column(String, nullable=False, unique=True)  # natural dedupe key
    event_type = Column(String)
    order_id = Column(String)
    payload = Column(Text)
    received_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime)
