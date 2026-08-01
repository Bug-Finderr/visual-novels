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
