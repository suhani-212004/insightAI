"""Regenerates the demo CSVs in this folder (deterministic, seed=42).

python sample_data/generate.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
out = Path(__file__).parent

# ---- Acme Retail: daily sales by region & category (2025-01 .. 2026-10) ----
days = pd.date_range("2025-01-01", "2026-10-31", freq="D")
regions = ["North", "South", "East", "West"]
categories = ["Electronics", "Apparel", "Home", "Grocery"]
base = {"Electronics": 900, "Apparel": 450, "Home": 600, "Grocery": 300}
rows = []
for d in days:
    season = 1 + 0.25 * np.sin(2 * np.pi * d.dayofyear / 365) + (0.35 if d.month in (11, 12) else 0)
    growth = 1 + 0.18 * ((d - days[0]).days / 365)
    for r in regions:
        for c in categories:
            units = max(1, int(rng.normal(20, 5) * season * growth))
            revenue = round(units * base[c] / 20 * rng.normal(1, 0.08), 2)
            rows.append({"order_date": d.date().isoformat(), "region": r, "category": c,
                         "units": units, "revenue": revenue, "discount_pct": round(rng.uniform(0, 0.25), 2)})
sales = pd.DataFrame(rows)
# plant a few anomalies for the detector to find
for idx in rng.choice(len(sales), 6, replace=False):
    sales.loc[idx, "revenue"] = round(sales.loc[idx, "revenue"] * rng.uniform(8, 15), 2)
sales.to_csv(out / "acme_sales.csv", index=False)

# ---- Acme Retail: marketing funnel by month & channel ----
months = pd.date_range("2025-01-01", "2026-10-01", freq="MS")
rows = []
for m in months:
    for ch in ["Organic", "Paid Search", "Social", "Email"]:
        visits = int(rng.normal(20000, 3000))
        signups = int(visits * rng.uniform(0.08, 0.14))
        trials = int(signups * rng.uniform(0.4, 0.6))
        purchases = int(trials * rng.uniform(0.2, 0.35))
        rows.append({"month": m.date().isoformat(), "channel": ch, "visits": visits, "signups": signups,
                     "trials": trials, "purchases": purchases, "spend_usd": round(rng.uniform(2000, 9000), 2)})
pd.DataFrame(rows).to_csv(out / "acme_marketing.csv", index=False)

# ---- Globex SaaS: subscriptions ----
rows = []
for i in range(1, 1201):
    start = pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 660)))
    plan = rng.choice(["Starter", "Growth", "Scale"], p=[0.55, 0.33, 0.12])
    mrr = {"Starter": 49, "Growth": 199, "Scale": 799}[plan]
    churned = rng.random() < 0.18
    rows.append({"customer_id": f"C{i:05d}", "signup_date": start.date().isoformat(), "plan": plan,
                 "country": rng.choice(["India", "USA", "UK", "Germany", "Brazil", "Japan"]),
                 "seats": int(rng.integers(1, 40)), "mrr_usd": mrr,
                 "churned": bool(churned), "nps": int(rng.integers(0, 11))})
pd.DataFrame(rows).to_csv(out / "globex_subscriptions.csv", index=False)
print("wrote", [p.name for p in out.glob("*.csv")])
