"""Creates two demo organisations with users, datasets and a dashboard.

Run from backend/:  python -m app.seed
Safe to re-run: it deletes the demo orgs/users first.

Logins (password for all: demo1234)
  owner@acme.example.com    - Owner,  Acme Retail (Pro plan)
  analyst@acme.example.com  - Admin,  Acme Retail
  viewer@acme.example.com   - Viewer, Acme Retail
  owner@globex.example.com  - Owner,  Globex SaaS (Free plan)
"""
import os
from pathlib import Path

import pandas as pd

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Dashboard, Membership, Organization, User, Widget
from app.services.anomaly import scan_dataset
from app.services.ingestion import ingest_frame
from app.services.orgs import create_org
from app.services.tenancy import drop_org_schema

DATA = Path(os.environ.get("SAMPLE_DATA_DIR", Path(__file__).resolve().parents[2] / "sample_data"))
PASSWORD = "demo1234"
USERS = ["owner@acme.example.com", "analyst@acme.example.com", "viewer@acme.example.com", "owner@globex.example.com"]

ACME_WIDGETS = [
    ("Monthly revenue", "line",
     "SELECT date_trunc('month', order_date)::date AS month, round(sum(revenue)) AS revenue "
     "FROM acme_sales GROUP BY 1 ORDER BY 1", "month", ["revenue"], None),
    ("Revenue by region", "bar",
     "SELECT region, round(sum(revenue)) AS revenue FROM acme_sales GROUP BY 1 ORDER BY 2 DESC",
     "region", ["revenue"], None),
    ("Category share", "pie",
     "SELECT category, round(sum(revenue)) AS revenue FROM acme_sales GROUP BY 1",
     "category", ["revenue"], None),
    ("Units vs revenue", "scatter",
     "SELECT units, revenue FROM acme_sales WHERE order_date >= '2026-09-01'",
     "units", ["revenue"], None),
    ("Region x category heatmap", "heatmap",
     "SELECT region, category, round(sum(revenue)) AS revenue FROM acme_sales GROUP BY 1, 2",
     "region", ["category"], "revenue"),
    ("Marketing funnel (2026)", "funnel",
     "SELECT stage, value FROM ("
     " SELECT 1 AS ord, 'Visits' AS stage, sum(visits) AS value FROM acme_marketing WHERE month >= '2026-01-01'"
     " UNION ALL SELECT 2, 'Signups', sum(signups) FROM acme_marketing WHERE month >= '2026-01-01'"
     " UNION ALL SELECT 3, 'Trials', sum(trials) FROM acme_marketing WHERE month >= '2026-01-01'"
     " UNION ALL SELECT 4, 'Purchases', sum(purchases) FROM acme_marketing WHERE month >= '2026-01-01'"
     ") f ORDER BY ord", "stage", ["value"], None),
]


def reset(db) -> None:
    demo = Organization.slug.in_(["acme-retail", "globex-saas"])
    for org in db.query(Organization).filter(demo).all():
        drop_org_schema(org.id)
    db.query(Organization).filter(demo).delete(synchronize_session=False)  # FK cascades clean the rest
    db.query(User).filter(User.email.in_(USERS)).delete(synchronize_session=False)
    db.commit()


def user(db, email: str, name: str) -> User:
    u = User(email=email, full_name=name, password_hash=hash_password(PASSWORD))
    db.add(u)
    db.flush()
    return u


def load(db, org_id: int, filename: str, name: str):
    return ingest_frame(db, org_id, pd.read_csv(DATA / filename), name=name, source_type="csv")


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        reset(db)

        # --- Acme Retail (Pro) ---
        owner = user(db, "owner@acme.example.com", "Asha Owner")
        acme = create_org(db, "Acme Retail", owner, plan="pro")
        db.add(Membership(user_id=user(db, "analyst@acme.example.com", "Ravi Analyst").id, org_id=acme.id, role="admin"))
        db.add(Membership(user_id=user(db, "viewer@acme.example.com", "Vik Viewer").id, org_id=acme.id, role="viewer"))
        db.commit()
        sales = load(db, acme.id, "acme_sales.csv", "acme_sales")
        load(db, acme.id, "acme_marketing.csv", "acme_marketing")
        scan_dataset(db, sales)

        dash = Dashboard(org_id=acme.id, name="Executive overview", layout=[])
        db.add(dash)
        db.flush()
        layout = []
        for i, (title, ctype, sql, x, y, value) in enumerate(ACME_WIDGETS):
            w = Widget(dashboard_id=dash.id, title=title, sql=sql,
                       chart={"type": ctype, "x": x, "y": y, "value": value})
            db.add(w)
            db.flush()
            layout.append({"i": str(w.id), "x": (i % 2) * 6, "y": (i // 2) * 8, "w": 6, "h": 8})
        dash.layout = layout
        db.commit()

        # --- Globex SaaS (Free) ---
        g_owner = user(db, "owner@globex.example.com", "Gita Owner")
        globex = create_org(db, "Globex SaaS", g_owner, plan="free")
        load(db, globex.id, "globex_subscriptions.csv", "subscriptions")
        g_dash = Dashboard(org_id=globex.id, name="Subscriptions", layout=[])
        db.add(g_dash)
        db.flush()
        w = Widget(dashboard_id=g_dash.id, title="MRR by plan",
                   sql="SELECT plan, sum(mrr_usd) AS mrr FROM subscriptions WHERE NOT churned GROUP BY 1 ORDER BY 2 DESC",
                   chart={"type": "bar", "x": "plan", "y": ["mrr"], "value": None})
        db.add(w)
        db.flush()
        g_dash.layout = [{"i": str(w.id), "x": 0, "y": 0, "w": 6, "h": 8}]
        db.commit()

        print(f"Seeded: Acme Retail (org {acme.id}, pro) and Globex SaaS (org {globex.id}, free).")
        print(f"Log in with owner@acme.example.com / {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
