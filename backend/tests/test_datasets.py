import io

import pandas as pd
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.ingestion import clean_frame, records_from_json, slugify
from tests.conftest import SALES_CSV, set_plan, signup, upload


def test_upload_creates_real_table_in_org_schema(client, owner):
    r = upload(client, owner)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["row_count"] == 30
    cols = {c["name"]: c["type"] for c in d["columns"]}
    assert cols == {"order_date": "timestamp", "region": "text", "revenue": "integer", "units": "integer"}

    p = client.get(f"/api/v1/datasets/{d['id']}/preview?limit=5", headers=owner).json()
    assert len(p["rows"]) == 5 and "order_date" in p["columns"]


def test_upload_rejects_non_csv_and_garbage(client, owner):
    r = client.post("/api/v1/datasets/upload", headers=owner,
                    files={"file": ("x.xlsx", io.BytesIO(b"abc"), "application/octet-stream")})
    assert r.status_code == 400
    r = client.post("/api/v1/datasets/upload", headers=owner,
                    files={"file": ("x.csv", io.BytesIO(b""), "text/csv")})
    assert r.status_code == 400


def test_dataset_limit_on_free_plan(client, owner):
    for i in range(3):
        assert upload(client, owner, name=f"d{i}").status_code == 201
    r = upload(client, owner, name="d4")
    assert r.status_code == 402
    set_plan(client, owner, "pro")
    assert upload(client, owner, name="d4").status_code == 201


def test_duplicate_names_get_unique_tables(client, owner):
    a = upload(client, owner, name="sales").json()
    b = upload(client, owner, name="sales").json()
    assert a["table_name"] == "sales" and b["table_name"] == "sales_2"


def test_delete_dataset_drops_table(client, owner):
    d = upload(client, owner).json()
    assert client.delete(f"/api/v1/datasets/{d['id']}", headers=owner).status_code == 204
    assert client.get(f"/api/v1/datasets/{d['id']}", headers=owner).status_code == 404
    r = client.post("/api/v1/query", headers=owner, json={"sql": "SELECT * FROM sales"})
    assert r.status_code == 400


def test_readonly_role_cannot_read_app_tables_or_write(client, owner):
    """Defence in depth: even if the SQL guard were bypassed, the DB role can't do damage."""
    upload(client, owner)
    ro = create_engine(settings.READONLY_DATABASE_URL)
    with ro.connect() as conn:
        for stmt in ("SELECT * FROM public.users", f"DELETE FROM org_{owner['X-Org-Id']}.sales"):
            try:
                conn.execute(text(stmt))
                raise AssertionError(f"read-only role was able to run: {stmt}")
            except Exception as e:  # permission denied / read-only transaction
                assert "denied" in str(e) or "read-only" in str(e)
            conn.rollback()
        rows = conn.execute(text(f"SELECT count(*) FROM org_{owner['X-Org-Id']}.sales")).scalar()
        assert rows == 30
    ro.dispose()


def test_clean_frame_helpers():
    assert slugify("Order Date ($)") == "order_date"
    assert slugify("1st col") == "_1st_col"
    assert slugify("select") == "select_"
    df = clean_frame(pd.DataFrame({"Amount": ["1,200", "300", "45"], "Amount ": [1, 2, 3], "Note": ["a", "b", None]}))
    assert list(df.columns) == ["amount", "amount_1", "note"]
    assert df["amount"].tolist() == [1200, 300, 45]
    assert records_from_json({"data": {"items": [{"a": 1}]}}, "data.items") == [{"a": 1}]
    assert records_from_json({"a": 1}) == [{"a": 1}]


def test_anomaly_scan_on_pro(client, owner):
    set_plan(client, owner, "pro")
    rows = ["day,value"] + [f"2026-01-{i:02d},{100 + (i % 5)}" for i in range(1, 29)] + ["2026-01-29,5000"]
    d = upload(client, owner, csv_text="\n".join(rows), name="metric").json()
    found = client.get(f"/api/v1/datasets/{d['id']}/anomalies", headers=owner).json()
    assert found and found[0]["value"] == 5000
    assert client.post(f"/api/v1/datasets/{d['id']}/anomalies/scan", headers=owner).status_code == 200


def test_anomaly_scan_gated_on_free(client, owner):
    d = upload(client, owner).json()
    assert client.post(f"/api/v1/datasets/{d['id']}/anomalies/scan", headers=owner).status_code == 402


def test_other_org_cannot_query_my_table(client, owner):
    upload(client, owner)
    other, _ = signup(client, email="x@globex.example.com", org="Globex")
    upload(client, other, csv_text=SALES_CSV, name="mine")
    r = client.post("/api/v1/query", headers=other, json={"sql": f"SELECT * FROM org_{owner['X-Org-Id']}.sales"})
    assert r.status_code == 400
    r = client.post("/api/v1/query", headers=other, json={"sql": "SELECT * FROM sales"})
    assert r.status_code == 400  # 'sales' is not one of Globex's tables
