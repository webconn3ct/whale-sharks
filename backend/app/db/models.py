import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """sa.Enum's default binds a Python Enum's .name, not .value — force .value
    so DB labels (lowercase for VariantEnum/ScanStatus) match what we write."""
    return Enum(enum_cls, name=name, values_callable=lambda obj: [e.value for e in obj])


class TimeframeEnum(str, enum.Enum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    ALL = "ALL"


class VariantEnum(str, enum.Enum):
    COMBINED = "combined"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL_TIME = "all_time"


class ScanStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Trader(Base):
    __tablename__ = "traders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    profile_image: Mapped[str | None] = mapped_column(Text)
    x_username: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TraderTrackRecord(Base):
    """Cached historical hit-rate stats computed from Polymarket's own
    /closed-positions data — refreshed on a TTL (see scan_service), not every
    scan, since a trader's resolved-position history changes slowly."""

    __tablename__ = "trader_track_records"

    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"), primary_key=True)
    win_rate: Mapped[float] = mapped_column(Numeric(5, 4))
    recent_form: Mapped[float] = mapped_column(Numeric(5, 4))
    sample_size: Mapped[int] = mapped_column(SmallInteger)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Market(Base):
    __tablename__ = "markets"

    condition_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    slug: Mapped[str] = mapped_column(String(255), default="")
    event_slug: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Gamma's `active`/`closed` — a market with no metadata (Gamma miss) defaults
    # to active=True so it isn't silently hidden by the active-only filter.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScanStatus] = mapped_column(pg_enum(ScanStatus, "scan_status"))
    traders_count: Mapped[int] = mapped_column(default=0)
    positions_count: Mapped[int] = mapped_column(default=0)
    total_value: Mapped[float] = mapped_column(Numeric(20, 6), default=0)
    error: Mapped[str | None] = mapped_column(Text)


class TraderLeaderboardRank(Base):
    __tablename__ = "trader_leaderboard_ranks"
    __table_args__ = (UniqueConstraint("scan_id", "trader_id", "timeframe"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    timeframe: Mapped[TimeframeEnum] = mapped_column(pg_enum(TimeframeEnum, "timeframe"))
    rank: Mapped[int] = mapped_column(SmallInteger)
    pnl: Mapped[float] = mapped_column(Numeric(18, 6))
    vol: Mapped[float] = mapped_column(Numeric(18, 6))

    trader: Mapped["Trader"] = relationship()


class ConsensusPosition(Base):
    __tablename__ = "consensus_positions"
    __table_args__ = (UniqueConstraint("scan_id", "variant", "top_n", "condition_id", "outcome_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    variant: Mapped[VariantEnum] = mapped_column(pg_enum(VariantEnum, "variant"), index=True)
    top_n: Mapped[int] = mapped_column(SmallInteger, index=True)
    condition_id: Mapped[str] = mapped_column(ForeignKey("markets.condition_id"))
    outcome_index: Mapped[int] = mapped_column(SmallInteger)
    outcome_label: Mapped[str] = mapped_column(String(100))
    current_price: Mapped[float] = mapped_column(Numeric(9, 6))
    whale_count: Mapped[int] = mapped_column()
    combined_value: Mapped[float] = mapped_column(Numeric(18, 6))
    consensus_score: Mapped[float] = mapped_column(Numeric(18, 6))

    market: Mapped["Market"] = relationship()
    traders: Mapped[list["ConsensusPositionTrader"]] = relationship(
        back_populates="consensus_position", cascade="all, delete-orphan"
    )


class ConsensusPositionTrader(Base):
    __tablename__ = "consensus_position_traders"
    __table_args__ = (UniqueConstraint("consensus_position_id", "trader_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    consensus_position_id: Mapped[int] = mapped_column(
        ForeignKey("consensus_positions.id", ondelete="CASCADE"), index=True
    )
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    best_timeframe: Mapped[TimeframeEnum] = mapped_column(pg_enum(TimeframeEnum, "best_timeframe"))
    best_rank: Mapped[int] = mapped_column(SmallInteger)
    position_value: Mapped[float] = mapped_column(Numeric(18, 6))
    size: Mapped[float] = mapped_column(Numeric(18, 6))
    avg_entry_price: Mapped[float] = mapped_column(Numeric(9, 6))
    current_price: Mapped[float] = mapped_column(Numeric(9, 6))
    cash_pnl: Mapped[float] = mapped_column(Numeric(18, 6))
    # Wider than the price columns above — a trader who entered at a few cents
    # can show a percent gain in the thousands, unlike price/probability fields.
    percent_pnl: Mapped[float] = mapped_column(Numeric(14, 6))
    # trader_weight at scan time — lets smaller top-N cuts be re-scored from
    # this stored (top_n=100) data without re-fetching track records.
    trader_weight: Mapped[float] = mapped_column(Numeric(18, 6))

    consensus_position: Mapped["ConsensusPosition"] = relationship(back_populates="traders")
    trader: Mapped["Trader"] = relationship()


class AppConfig(Base):
    """Singleton row (id always 1) holding mutable site config editable from
    the admin panel — access/admin credentials and tunable scoring weights."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    access_code_hash: Mapped[str] = mapped_column(Text)
    admin_password_hash: Mapped[str] = mapped_column(Text)
    value_normalizer: Mapped[float] = mapped_column(Numeric(6, 3), default=6.0)
    max_value_boost: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExcludedMarket(Base):
    """Content moderation: condition_ids hidden from the public dashboard."""

    __tablename__ = "excluded_markets"

    condition_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    excluded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExcludedTrader(Base):
    """Content moderation: wallets hidden from the public dashboard."""

    __tablename__ = "excluded_traders"

    wallet_address: Mapped[str] = mapped_column(String(42), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    excluded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
