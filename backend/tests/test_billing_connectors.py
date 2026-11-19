import httpx
import pytest

from app.core.config import settings
from app.models import Connector, Organization
from app.services import billing
from app.services.anomaly import detect
from app.services.connectors import due_connectors, poll_connector
from app.services.plans import PLANS
from tests.conftest import set_plan


# ---------------- billing ----------------
def test_plan_endpoint_and_dev_switch(client, owner):
    r = client.get("/api/v1/billing", headers=owner).json()
    assert r["plan"] == "free" and r["stripe_enabled"] is False
    assert "pdf_export" not in r["limits"]["features"]
    set_plan(client, owner, "pro")
    assert client.get("/api/v1/billing", headers=owner).json()["plan"] == "pro"
    assert client.post("/api/v1/billing/dev/set-plan", headers=owner, json={"plan": "gold"}).status_code == 400
    assert set(client.get("/api/v1/billing/plans").json()) == set(PLANS)


def test_checkout_needs_stripe(client, owner):
    assert client.post("/api/v1/billing/checkout", headers=owner, json={"plan": "pro"}).status_code == 503
    assert client.post("/api/v1/billing/portal", headers=owner).status_code == 503


def test_webhook_rejects_bad_signature(client):
    r = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=bad"})
    assert r.status_code == 400


def test_stripe_events_update_plan(client, owner, db, monkeypatch):
    org_id = int(owner["X-Org-Id"])
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ENTERPRISE", "price_ent")

    billing.handle_event(db, {"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": str(org_id), "customer": "cus_1", "subscription": "sub_1",
        "metadata": {"org_id": str(org_id), "plan": "pro"}}}})
    org = db.get(Organization, org_id)
    assert org.plan == "pro" and org.stripe_customer_id == "cus_1"

    billing.handle_event(db, {"type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {},
        "items": {"data": [{"price": {"id": "price_ent"}}]}}}})
    db.refresh(org)
    assert org.plan == "enterprise"

    billing.handle_event(db, {"type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "metadata": {"org_id": str(org_id)}}}})
    db.refresh(org)
    assert org.plan == "free" and org.stripe_subscription_id is None

    assert billing.handle_event(db, {"type": "invoice.paid", "data": {"object": {}}}) is None
    assert billing.plan_for_price("unknown") == "free"
    with pytest.raises(ValueError):
        monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", None)
        billing.price_for("pro")


def test_only_owner_can_change_plan(client, owner):
    client.post("/api/v1/orgs/members", headers=owner,
                json={"email": "adm@acme.example.com", "role": "admin", "password": "password123"})
    tok = client.post("/api/v1/auth/login", json={"email": "adm@acme.example.com", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}", "X-Org-Id": owner["X-Org-Id"]}
    assert client.post("/api/v1/billing/dev/set-plan", headers=h, json={"plan": "pro"}).status_code == 403


# ---------------- connectors ----------------
def test_connectors_gated_on_free(client, owner):
    r = client.post("/api/v1/connectors", headers=owner,
                    json={"dataset_name": "events", "type": "webhook"})
    assert r.status_code == 402


def test_webhook_connector_ingests_and_appends(client, owner):
    set_plan(client, owner, "pro")
    c = client.post("/api/v1/connectors", headers=owner, json={"dataset_name": "events", "type": "webhook"}).json()
    url = c["webhook_url"]

    r = client.post(url, json=[{"event": "signup", "amount": 10}, {"event": "buy", "amount": 25}])
    assert r.status_code == 202 and r.json()["row_count"] == 2
    r = client.post(url, json={"event": "buy", "amount": 5, "extra": "ignored"})
    assert r.json()["row_count"] == 3

    q = client.post("/api/v1/query", headers=owner, json={"sql": "SELECT sum(amount) AS s FROM events"}).json()
    assert q["rows"] == [{"s": 40}]

    assert client.post(url.rsplit("/", 1)[0] + "/wrong-secret", json=[{"a": 1}]).status_code == 404
    assert client.post(url, json="not-json-object").status_code == 400
    assert len(client.get("/api/v1/connectors", headers=owner).json()) == 1
    assert client.delete(f"/api/v1/connectors/{c['id']}", headers=owner).status_code == 204


def test_api_poll_connector(client, owner, db):
    set_plan(client, owner, "pro")
    bad = client.post("/api/v1/connectors", headers=owner,
                      json={"dataset_name": "fx", "type": "api_poll", "url": "ftp://x"})
    assert bad.status_code == 400
    c = client.post("/api/v1/connectors", headers=owner, json={
        "dataset_name": "fx", "type": "api_poll", "url": "https://api.example.com/rates",
        "json_path": "data", "interval_minutes": 5}).json()

    payload = {"data": [{"currency": "INR", "rate": 83.1}, {"currency": "EUR", "rate": 0.92}]}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    conn = db.get(Connector, c["id"])
    assert conn in due_connectors(db)
    assert poll_connector(db, conn, client=httpx.Client(transport=transport)) == 2
    assert conn.last_status == "ok: 2 rows"
    assert conn not in due_connectors(db)

    failing = httpx.MockTransport(lambda req: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        poll_connector(db, conn, client=httpx.Client(transport=failing))
    assert conn.last_status.startswith("error")

    # "Run now" endpoint records the failure instead of crashing (no network in tests)
    r = client.post(f"/api/v1/connectors/{c['id']}/run", headers=owner)
    assert r.status_code == 200 and r.json()["last_status"]


# ---------------- anomaly detector ----------------
def test_detect_flags_outliers_only():
    import pandas as pd

    normal = pd.DataFrame({"v": [10, 11, 9, 10, 12, 11, 10, 9, 10, 11]})
    assert detect(normal) == []
    spiked = pd.DataFrame({"v": [10, 11, 9, 10, 12, 11, 10, 9, 10, 11, 400], "label": list("abcdefghijk")})
    hits = detect(spiked)
    assert len(hits) == 1 and hits[0]["value"] == 400 and hits[0]["row_index"] == 10
    assert detect(pd.DataFrame({"v": [1, 2, 3]})) == []


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
