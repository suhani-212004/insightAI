"""Test setup: a real Postgres test database (schemas are a Postgres feature).

Set TEST_DATABASE_URL / TEST_READONLY_DATABASE_URL or use the docker-compose defaults.
"""
import io
import os

os.environ.setdefault("ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://insight:insight@127.0.0.1:5432/insight_test"
)
os.environ["READONLY_DATABASE_URL"] = os.environ.get(
    "TEST_READONLY_DATABASE_URL", "postgresql+psycopg2://insight_readonly:insight_ro@127.0.0.1:5432/insight_test"
)
os.environ["OPENAI_API_KEY"] = ""
os.environ["STRIPE_SECRET_KEY"] = ""

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ai_query  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean():
    yield
    with engine.begin() as conn:
        for (schema,) in conn.execute(text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'org\\_%'")):
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    ai_query.set_generator(None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def signup(client, email="owner@acme.example.com", org="Acme", password="password123"):
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": password, "org_name": org})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}", "X-Org-Id": str(data["orgs"][0]["id"])}, data


def set_plan(client, headers, plan):
    r = client.post("/api/v1/billing/dev/set-plan", headers=headers, json={"plan": plan})
    assert r.status_code == 200, r.text


SALES_CSV = "\n".join(
    ["Order Date,Region,Revenue,Units"]
    + [f"2026-0{1 + i % 6}-1{i % 9},{['North', 'South', 'East'][i % 3]},{100 + i},{i % 7 + 1}" for i in range(30)]
)


def upload(client, headers, csv_text=SALES_CSV, name="sales"):
    return client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": (f"{name}.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        data={"name": name},
    )


@pytest.fixture
def owner(client):
    headers, data = signup(client)
    return headers


@pytest.fixture
def frame():
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
