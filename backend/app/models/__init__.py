"""SQLAlchemy models for the shared `public` schema.

Tenant *data* (uploaded datasets) does NOT live here: each organisation gets its
own Postgres schema `org_<id>` with one real table per dataset.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free|pro|enterprise
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

    @property
    def schema_name(self) -> str:
        return f"org_{self.id}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # owner|admin|viewer

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("org_id", "table_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    table_name: Mapped[str] = mapped_column(String(63))
    source_type: Mapped[str] = mapped_column(String(20), default="csv")  # csv|api_poll|webhook
    columns: Mapped[list] = mapped_column(JSON, default=list)  # [{"name":..,"type":..}]
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))  # api_poll|webhook
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # api_poll: {url, interval_minutes, json_path}
    secret: Mapped[str] = mapped_column(String(64))  # webhook path secret
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    layout: Mapped[list] = mapped_column(JSON, default=list)  # react-grid-layout items
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    widgets: Mapped[list["Widget"]] = relationship(back_populates="dashboard", cascade="all, delete-orphan")


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    sql: Mapped[str] = mapped_column(Text)
    chart: Mapped[dict] = mapped_column(JSON)  # {type, x, y:[...], ...}

    dashboard: Mapped[Dashboard] = relationship(back_populates="widgets")


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"))
    frequency: Mapped[str] = mapped_column(String(10), default="daily")  # daily|weekly
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rows: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    column: Mapped[str] = mapped_column(String(63))
    row_index: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(10))  # zscore|iqr
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageCounter(Base):
    """Per-org daily counters used for plan limits (e.g. AI queries per day)."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("org_id", "metric", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    count: Mapped[int] = mapped_column(Integer, default=0)
