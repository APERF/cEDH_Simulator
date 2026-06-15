from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from app.db.database import Base


class CardData(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scryfall_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    mana_cost: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cmc: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_line: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    oracle_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    colors: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    color_identity: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    power: Mapped[str | None] = mapped_column(String(10), nullable=True)
    toughness: Mapped[str | None] = mapped_column(String(10), nullable=True)
    image_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    layout: Mapped[str | None] = mapped_column(String(50), nullable=True)
    effects_json: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    last_synced: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
