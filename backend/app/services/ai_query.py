"""Natural-language analytics: question -> SQL -> rows -> chart spec.

Pipeline for each question:
  1. Describe the org's tables (columns, types, a few sample rows).
  2. Send schema + recent chat history + question to the LLM (LangChain + OpenAI),
     asking for structured output: {sql, chart, explanation}.
  3. Validate and run the SQL (sql_guard + query_runner).
  4. If it fails, send the error back to the LLM once and retry.
  5. Save both messages so the next question has conversational memory.
"""
from __future__ import annotations

import json
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.models import ChatMessage, ChatSession, Dataset
from app.services.query_runner import run_tenant_query
from app.services.sql_guard import UnsafeSQL
from app.services.tenancy import safe_ident, schema_for

HISTORY_TURNS = 10

SYSTEM_PROMPT = """You are a senior data analyst who writes PostgreSQL for a BI dashboard.

You can ONLY query these tables (unqualified names, no schema prefix):
{schema}

Rules:
- Write exactly ONE read-only SELECT statement. CTEs are fine. Never modify data.
- Use only the tables and columns listed above. Quote nothing unless needed.
- Aggregate for charts (GROUP BY) and ORDER BY the x-axis for time series.
- Use date_trunc('month', col) etc. for time buckets and alias columns clearly.
- Keep results small (< 200 rows) unless the user asks for raw rows.
- If the question is a follow-up ("now filter that by...", "same but per region"),
  build on the previous SQL in the conversation.
- If the question cannot be answered from these tables, set sql to null and explain why.

Pick a chart:
- line: trend over time. bar: compare categories. pie: share of a whole (<= 8 slices).
- scatter: relationship between two numbers. heatmap: two categorical axes + a numeric value.
- funnel: ordered stages with decreasing counts. table: anything else / raw rows.
Set chart.x to the x / category column alias, chart.y to the numeric column alias(es).
For heatmap set x, y=[second axis column], value=numeric column."""


class ChartOut(BaseModel):
    type: Literal["line", "bar", "pie", "scatter", "heatmap", "funnel", "table"] = "table"
    x: str | None = None
    y: list[str] = Field(default_factory=list)
    value: str | None = None


class AIAnswer(BaseModel):
    sql: str | None = Field(description="One PostgreSQL SELECT statement, or null if not answerable")
    chart: ChartOut = Field(default_factory=ChartOut)
    explanation: str = Field(description="One or two sentences for the user explaining the result")


class SQLGenerator(Protocol):
    def generate(self, question: str, schema: str, history: list[dict], error: str | None = None) -> AIAnswer: ...


class OpenAIGenerator:
    """LangChain + OpenAI with structured (JSON-schema) output."""

    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0, api_key=settings.OPENAI_API_KEY)
        self.llm = llm.with_structured_output(AIAnswer)

    def generate(self, question, schema, history, error=None) -> AIAnswer:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        msgs = [SystemMessage(SYSTEM_PROMPT.format(schema=schema))]
        for h in history:
            if h["role"] == "user":
                msgs.append(HumanMessage(h["content"]))
            else:
                msgs.append(AIMessage(json.dumps({"sql": h.get("sql"), "explanation": h["content"]})))
        msgs.append(HumanMessage(question))
        if error:
            msgs.append(HumanMessage(f"That SQL failed with this error, fix it and try again:\n{error}"))
        return self.llm.invoke(msgs)


class NoKeyGenerator:
    """Used when OPENAI_API_KEY is missing so the app still runs in a demo."""

    def generate(self, question, schema, history, error=None) -> AIAnswer:
        first_table = schema.split("\n", 1)[0].removeprefix("TABLE ").split(" ", 1)[0].strip()
        if not first_table or first_table.startswith("("):
            return AIAnswer(sql=None, explanation="Upload a dataset first, then ask a question.")
        return AIAnswer(
            sql=f"SELECT * FROM {first_table} LIMIT 20",
            chart=ChartOut(type="table"),
            explanation="OPENAI_API_KEY is not set, so here are sample rows instead of an AI answer. "
            "Add the key to backend/.env to enable Text-to-SQL.",
        )


_generator: SQLGenerator | None = None


def get_generator() -> SQLGenerator:
    global _generator
    if _generator is None:
        _generator = OpenAIGenerator() if settings.OPENAI_API_KEY else NoKeyGenerator()
    return _generator


def set_generator(gen: SQLGenerator | None) -> None:
    """Swap the generator (used by tests)."""
    global _generator
    _generator = gen


def describe_schema(db: Session, org_id: int, sample_rows: int = 3) -> str:
    datasets = [d for d in db.query(Dataset).filter_by(org_id=org_id).order_by(Dataset.id).all() if d.columns]
    if not datasets:
        return "(no tables yet)"
    schema = schema_for(org_id)
    parts = []
    with engine.connect() as conn:
        for d in datasets:
            cols = ", ".join(f"{c['name']} {c['type']}" for c in d.columns)
            parts.append(f"TABLE {d.table_name} ({cols})  -- {d.name}, {d.row_count} rows")
            rows = conn.execute(
                text(f'SELECT * FROM "{schema}"."{safe_ident(d.table_name)}" LIMIT :n'), {"n": sample_rows}
            ).mappings()
            for r in rows:
                parts.append("  sample: " + json.dumps({k: str(v) for k, v in r.items()})[:400])
    return "\n".join(parts)


def _infer_chart(chart: ChartOut, columns: list[str], rows: list[dict]) -> dict:
    """Fill in missing / wrong axis names so the frontend can always render."""
    spec = chart.model_dump()
    if not columns:
        spec["type"] = "table"
        return spec
    numeric = [c for c in columns if rows and isinstance(rows[0].get(c), (int, float))]
    if spec.get("x") not in columns:
        non_numeric = [c for c in columns if c not in numeric]
        spec["x"] = non_numeric[0] if non_numeric else columns[0]
    spec["y"] = [y for y in spec.get("y") or [] if y in columns] or [c for c in numeric if c != spec["x"]][:3]
    if spec["type"] == "heatmap" and spec.get("value") not in columns:
        spec["value"] = numeric[-1] if numeric else None
    if spec["type"] != "table" and not spec["y"] and spec["type"] != "heatmap":
        spec["type"] = "table"
    return spec


def _history(session: ChatSession) -> list[dict]:
    msgs = session.messages[-HISTORY_TURNS * 2 :]
    return [{"role": m.role, "content": m.content, "sql": m.sql} for m in msgs]


def ask(db: Session, org_id: int, user_id: int, question: str, session_id: int | None = None) -> ChatMessage:
    if session_id:
        session = db.query(ChatSession).filter_by(id=session_id, org_id=org_id, user_id=user_id).first()
        if not session:
            raise LookupError("Chat session not found")
    else:
        session = ChatSession(org_id=org_id, user_id=user_id, title=question[:80])
        db.add(session)
        db.flush()

    history = _history(session)
    schema = describe_schema(db, org_id)
    gen = get_generator()

    db.add(ChatMessage(session_id=session.id, role="user", content=question))

    answer = gen.generate(question, schema, history)
    result, error = None, None
    for attempt in range(2):
        if not answer.sql:
            break
        try:
            result = run_tenant_query(db, org_id, answer.sql, limit=500)
            error = None
            break
        except (UnsafeSQL, DBAPIError) as e:
            error = str(getattr(e, "orig", e)).split("\n")[0]
            if attempt == 0:
                answer = gen.generate(question, schema, history, error=f"SQL: {answer.sql}\nError: {error}")

    if result is not None:
        msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer.explanation,
            sql=result["sql"],
            chart=_infer_chart(answer.chart, result["columns"], result["rows"]),
            rows=result["rows"],
        )
    else:
        content = answer.explanation if not error else f"I couldn't run that query: {error}"
        msg = ChatMessage(session_id=session.id, role="assistant", content=content, sql=answer.sql)

    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
