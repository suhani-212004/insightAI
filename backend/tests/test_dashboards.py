from tests.conftest import set_plan, upload

WIDGET = {
    "title": "Revenue by region",
    "sql": "SELECT region, sum(revenue) AS revenue FROM sales GROUP BY 1 ORDER BY 1",
    "chart": {"type": "bar", "x": "region", "y": ["revenue"]},
}


def make_dash(client, h, name="Main"):
    r = client.post("/api/v1/dashboards", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_dashboard_widget_lifecycle(client, owner):
    upload(client, owner)
    d = make_dash(client, owner)

    w = client.post(f"/api/v1/dashboards/{d['id']}/widgets", headers=owner, json=WIDGET)
    assert w.status_code == 201, w.text
    wid = w.json()["id"]

    data = client.get(f"/api/v1/widgets/{wid}/data", headers=owner).json()
    assert data["columns"] == ["region", "revenue"] and len(data["rows"]) == 3

    full = client.get(f"/api/v1/dashboards/{d['id']}", headers=owner).json()
    assert full["layout"][0]["i"] == str(wid)

    new_layout = [{"i": str(wid), "x": 6, "y": 0, "w": 4, "h": 6}, {"i": "999", "x": 0, "y": 0, "w": 1, "h": 1}]
    r = client.put(f"/api/v1/dashboards/{d['id']}/layout", headers=owner, json={"layout": new_layout})
    assert r.json()["layout"] == [new_layout[0]]  # unknown widget ids are dropped

    upd = {**WIDGET, "title": "Renamed", "chart": {"type": "pie", "x": "region", "y": ["revenue"]}}
    assert client.put(f"/api/v1/widgets/{wid}", headers=owner, json=upd).json()["title"] == "Renamed"

    assert client.patch(f"/api/v1/dashboards/{d['id']}", headers=owner, json={"name": "Ops"}).json()["name"] == "Ops"
    assert client.delete(f"/api/v1/widgets/{wid}", headers=owner).status_code == 204
    assert client.get(f"/api/v1/dashboards/{d['id']}", headers=owner).json()["layout"] == []
    assert client.delete(f"/api/v1/dashboards/{d['id']}", headers=owner).status_code == 204
    assert client.get("/api/v1/dashboards", headers=owner).json() == []


def test_widget_with_unsafe_sql_rejected(client, owner):
    upload(client, owner)
    d = make_dash(client, owner)
    bad = {**WIDGET, "sql": "DELETE FROM sales"}
    assert client.post(f"/api/v1/dashboards/{d['id']}/widgets", headers=owner, json=bad).status_code == 400
    bad = {**WIDGET, "sql": "SELECT nope FROM sales"}
    r = client.post(f"/api/v1/dashboards/{d['id']}/widgets", headers=owner, json=bad)
    assert r.status_code == 400 and "nope" in r.json()["detail"]


def test_query_row_limit_and_colons(client, owner):
    upload(client, owner)
    r = client.post("/api/v1/query", headers=owner,
                    json={"sql": "SELECT '10:30' AS t, order_date::date AS d FROM sales"})
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["t"] == "10:30"


def test_dashboard_limit_free(client, owner):
    make_dash(client, owner, "a")
    make_dash(client, owner, "b")
    assert client.post("/api/v1/dashboards", headers=owner, json={"name": "c"}).status_code == 402


def test_pdf_export_and_schedule_gates(client, owner):
    d = make_dash(client, owner)
    assert client.post(f"/api/v1/dashboards/{d['id']}/export", headers=owner).status_code == 402
    r = client.post(f"/api/v1/dashboards/{d['id']}/schedules", headers=owner, json={"frequency": "daily"})
    assert r.status_code == 402

    set_plan(client, owner, "enterprise")
    r = client.post(f"/api/v1/dashboards/{d['id']}/schedules", headers=owner,
                    json={"frequency": "weekly", "recipients": ["boss@acme.example.com"]})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert len(client.get(f"/api/v1/dashboards/{d['id']}/schedules", headers=owner).json()) == 1
    assert client.delete(f"/api/v1/schedules/{sid}", headers=owner).status_code == 204


def test_missing_resources_404(client, owner):
    assert client.get("/api/v1/dashboards/123", headers=owner).status_code == 404
    assert client.get("/api/v1/widgets/123/data", headers=owner).status_code == 404
    assert client.delete("/api/v1/schedules/123", headers=owner).status_code == 404
