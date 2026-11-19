"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["owner", "admin", "viewer"]
ChartType = Literal["line", "bar", "pie", "scatter", "heatmap", "funnel", "table"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    org_name: str = Field(min_length=2, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class OrgBrief(ORM):
    id: int
    name: str
    slug: str
    plan: str
    role: Role


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"
    orgs: list[OrgBrief]


class UserOut(ORM):
    id: int
    email: str
    full_name: str


# ---------- orgs ----------
class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class MemberOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: Role


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = "viewer"
    password: str | None = Field(default=None, min_length=8)  # demo: create the user if missing


class RoleUpdate(BaseModel):
    role: Role


# ---------- datasets ----------
class ColumnInfo(BaseModel):
    name: str
    type: str


class DatasetOut(ORM):
    id: int
    name: str
    table_name: str
    source_type: str
    columns: list[ColumnInfo]
    row_count: int
    created_at: datetime
    updated_at: datetime


class ConnectorIn(BaseModel):
    dataset_name: str = Field(min_length=1, max_length=120)
    type: Literal["api_poll", "webhook"]
    url: str | None = None
    interval_minutes: int = Field(default=60, ge=1)
    json_path: str | None = None  # e.g. "data.items"


class ConnectorOut(ORM):
    id: int
    dataset_id: int
    type: str
    config: dict
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    webhook_url: str | None = None


# ---------- charts / dashboards ----------
class ChartSpec(BaseModel):
    type: ChartType
    x: str | None = None
    y: list[str] = []
    # heatmap: x, y[0] are the two axes, `value` the colour
    value: str | None = None


class WidgetIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    sql: str
    chart: ChartSpec


class WidgetOut(ORM):
    id: int
    title: str
    sql: str
    chart: dict


class DashboardIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DashboardOut(ORM):
    id: int
    name: str
    layout: list
    widgets: list[WidgetOut] = []


class LayoutIn(BaseModel):
    layout: list[dict]


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict]
    truncated: bool = False


class ScheduleIn(BaseModel):
    frequency: Literal["daily", "weekly"] = "weekly"
    recipients: list[EmailStr] = []


class ScheduleOut(ORM):
    id: int
    dashboard_id: int
    frequency: str
    recipients: list
    last_sent_at: datetime | None


# ---------- AI ----------
class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: int | None = None


class ChatMessageOut(ORM):
    id: int
    role: str
    content: str
    sql: str | None
    chart: dict | None
    rows: list | None
    created_at: datetime


class ChatSessionOut(ORM):
    id: int
    title: str
    created_at: datetime


class AskOut(BaseModel):
    session_id: int
    message: ChatMessageOut


# ---------- anomalies ----------
class AnomalyOut(ORM):
    id: int
    dataset_id: int
    column: str
    row_index: int
    value: float
    score: float
    method: str
    detected_at: datetime


# ---------- billing ----------
class PlanOut(BaseModel):
    plan: str
    limits: dict
    usage: dict
    stripe_enabled: bool


class CheckoutIn(BaseModel):
    plan: Literal["pro", "enterprise"]


TokenOut.model_rebuild()
