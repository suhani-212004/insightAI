"""Tests for the security / reliability fixes and the shared helpers they introduced."""
import httpx
import pytest
from fastapi import HTTPException

from app.api.deps import get_owned
from app.core import config
from app.core.database import session_scope
from app.models import Connector, Dataset, Organization, UsageCounter
from app.services import ai_query
from app.services.ai_query import AIAnswer, LLMUnavailable
from app.services.connectors import BlockedURL, check_public_url, poll_connector
from app.services.plans import has_feature
from app.workers import tasks
from tests.conftest import set_plan, signup, upload


# ---------- tenant isolation helper ----------
def test_get_owned_hides_other_orgs_rows(client, owner, db):
    upload(client, owner)
    other, _ = signup(client, email="eve@globex.example.com", org="Globex")
    dataset_id = client.get("/api/v1/datasets", headers=owner).json()[0]["id"]

    assert client.get(f"/api/v1/datasets/{dataset_id}", headers=other).status_code == 404
    with pytest.raises(HTTPException) as e:
        get_owned(db, Dataset, dataset_id, org_id=int(other["X-Org-Id"]))
    assert e.value.status_code == 404 and e.value.detail == "Dataset not found"
    assert get_owned(db, Dataset, dataset_id, org_id=int(owner["X-Org-Id"])).id == dataset_id


def test_list_endpoints_paginate(client, owner):
    set_plan(client, owner, "pro")
    for name in ("a", "b", "c"):
        upload(client, owner, name=name)
    page1 = client.get("/api/v1/datasets?limit=2", headers=owner).json()
    page2 = client.get("/api/v1/datasets?limit=2&offset=2", headers=owner).json()
    assert len(page1) == 2 and len(page2) == 1
    assert {d["name"] for d in page1 + page2} == {"a", "b", "c"}
    assert client.get("/api/v1/datasets?limit=0", headers=owner).status_code == 422
    assert client.get("/api/v1/datasets?limit=10000", headers=owner).status_code == 422


# ---------- auth ----------
def test_token_in_query_string_only_works_for_stream(client, owner):
    token = owner["Authorization"].split(" ", 1)[1]
    r = client.get(f"/api/v1/datasets?token={token}", headers={"X-Org-Id": owner["X-Org-Id"]})
    assert r.status_code == 401


def test_prod_refuses_default_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_settings.__wrapped__()
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    assert config.get_settings.__wrapped__().ENV == "prod"


# ---------- LLM failures ----------
class FailingGen:
    def generate(self, question, schema, history, error=None):
        raise LLMUnavailable("rate limited")


class QueueGen:
    def __init__(self, *answers):
        self.answers = list(answers)

    def generate(self, question, schema, history, error=None):
        return self.answers.pop(0)


def _ai_count(db, org_id):
    db.expire_all()
    c = db.query(UsageCounter).filter_by(org_id=org_id, metric="ai_queries").first()
    return c.count if c else 0


def test_llm_outage_returns_503_and_refunds_quota(client, owner, db):
    upload(client, owner)
    ai_query.set_generator(FailingGen())
    r = client.post("/api/v1/ai/ask", headers=owner, json={"question": "revenue?"})
    assert r.status_code == 503
    assert _ai_count(db, int(owner["X-Org-Id"])) == 0
    # nothing half-saved: no empty chat session left behind
    assert client.get("/api/v1/ai/sessions", headers=owner).json() == []


def test_retry_that_gives_up_does_not_show_stale_error(client, owner):
    upload(client, owner)
    ai_query.set_generator(QueueGen(
        AIAnswer(sql="SELECT nope FROM sales", explanation="first try"),
        AIAnswer(sql=None, explanation="That column doesn't exist in your data."),
    ))
    msg = client.post("/api/v1/ai/ask", headers=owner, json={"question": "nope?"}).json()["message"]
    assert msg["content"] == "That column doesn't exist in your data."


def test_openai_generator_wraps_errors():
    class Boom:
        def invoke(self, msgs):
            raise TimeoutError("read timeout")

    class Empty:
        def invoke(self, msgs):
            return None

    gen = ai_query.OpenAIGenerator.__new__(ai_query.OpenAIGenerator)  # skip creating a real client
    for llm in (Boom(), Empty()):
        gen.llm = llm
        with pytest.raises(LLMUnavailable):
            gen.generate("q", "TABLE t (a integer)", [])


def test_schema_description_is_capped(client, owner, db, monkeypatch):
    upload(client, owner)
    monkeypatch.setattr(ai_query, "MAX_SCHEMA_CHARS", 50)
    out = ai_query.describe_schema(db, int(owner["X-Org-Id"]))
    assert out.endswith("(schema truncated)") and len(out) < 80


# ---------- connectors ----------
@pytest.mark.parametrize("url", [
    "http://localhost:8000/api", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data",
    "http://10.1.2.3/", "http://[::1]/", "http://db.internal/", "ftp://example.com/",
])
def test_internal_urls_are_blocked(url):
    with pytest.raises(BlockedURL):
        check_public_url(url, resolve=False)


def test_public_ip_is_allowed():
    check_public_url("https://8.8.8.8/data", resolve=False)


def test_connector_cannot_target_internal_network(client, owner):
    set_plan(client, owner, "pro")
    r = client.post("/api/v1/connectors", headers=owner, json={
        "dataset_name": "meta", "type": "api_poll", "url": "http://169.254.169.254/latest"})
    assert r.status_code == 400 and "Internal" in r.json()["detail"]


def test_webhook_type_clash_is_a_400_not_a_500(client, owner):
    set_plan(client, owner, "pro")
    url = client.post("/api/v1/connectors", headers=owner,
                      json={"dataset_name": "events", "type": "webhook"}).json()["webhook_url"]
    assert client.post(url, json=[{"amount": 10}, {"amount": 20}]).status_code == 202
    r = client.post(url, json=[{"amount": "not a number"}])
    assert r.status_code == 400 and "don't match" in r.json()["detail"]
    # the dataset is still usable afterwards
    assert client.post(url, json=[{"amount": 5}]).json()["row_count"] == 3


def test_webhook_stops_after_downgrade(client, owner):
    set_plan(client, owner, "pro")
    url = client.post("/api/v1/connectors", headers=owner,
                      json={"dataset_name": "events", "type": "webhook"}).json()["webhook_url"]
    set_plan(client, owner, "free")
    assert client.post(url, json=[{"a": 1}]).status_code == 402


def test_failed_poll_leaves_session_usable(client, owner, db):
    set_plan(client, owner, "pro")
    c = client.post("/api/v1/connectors", headers=owner, json={
        "dataset_name": "fx", "type": "api_poll", "url": "https://api.example.com/rates"}).json()
    conn = db.get(Connector, c["id"])
    bad_json = httpx.MockTransport(lambda req: httpx.Response(200, content=b"<html>not json"))
    with pytest.raises(ValueError):
        poll_connector(db, conn, client=httpx.Client(transport=bad_json))
    db.refresh(conn)
    assert conn.last_status.startswith("error")
    assert db.query(Connector).count() == 1  # session still works


# ---------- shared helpers ----------
def test_session_scope_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with session_scope() as s:
            s.add(Organization(name="Ghost", slug="ghost"))
            s.flush()
            raise RuntimeError("boom")
    assert db.query(Organization).filter_by(slug="ghost").first() is None

    with session_scope() as s:
        s.add(Organization(name="Real", slug="real"))
    assert db.query(Organization).filter_by(slug="real").first() is not None


def test_unknown_plan_falls_back_to_free():
    org = Organization(name="x", slug="x", plan="platinum-typo")
    assert has_feature(org, "csv_upload") and not has_feature(org, "webhooks")


def test_worker_units_tolerate_missing_rows():
    assert tasks._poll_one(999_999) is False
    assert tasks._scan_one(999_999) is False
