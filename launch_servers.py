import os
import threading
import socketserver
import http.server
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ----------------- PORT 8000: FASTAPI APP -----------------
api_app = FastAPI(
    title="InsightAI API",
    version="1.0.0",
    description="InsightAI Multi-Tenant AI-Augmented Analytics SaaS API (Swagger UI)",
    docs_url="/docs",
    redoc_url="/redoc"
)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api_app.get("/health")
def health():
    return {"status": "ok", "app": "InsightAI API v1.0.0"}

class LoginReq(BaseModel):
    email: str
    password: str

@api_app.post("/api/v1/auth/login")
def login(req: LoginReq):
    return {
        "access_token": "mock-jwt-token-insightai",
        "token_type": "bearer",
        "user": {"email": req.email, "role": "owner"}
    }

@api_app.get("/api/v1/auth/me")
def me():
    return {
        "id": 1,
        "email": "owner@acme.example.com",
        "role": "owner",
        "organization": {
            "id": 1,
            "name": "Acme Retail",
            "plan": "pro"
        }
    }

@api_app.get("/api/v1/datasets")
def list_datasets():
    return [
        {
            "id": 1,
            "name": "acme_sales",
            "rows": 1500,
            "columns": ["order_id", "customer_id", "sale_date", "amount", "category", "region"],
            "anomalies_count": 1
        },
        {
            "id": 2,
            "name": "acme_marketing",
            "rows": 1920,
            "columns": ["campaign", "clicks", "impressions", "spend", "conversions"],
            "anomalies_count": 0
        }
    ]

class AIAskReq(BaseModel):
    question: str
    session_id: int | None = None

@api_app.post("/api/v1/ai/ask")
def ai_ask(req: AIAskReq):
    return {
        "answer": f"Executed query for: '{req.question}'. North America produced the highest revenue ($88,400).",
        "sql": "SELECT region, sum(amount) AS total_revenue FROM org_1.acme_sales GROUP BY region ORDER BY total_revenue DESC;",
        "chart": {
            "type": "bar",
            "x": "region",
            "y": ["total_revenue"]
        },
        "rows": [
            {"region": "North America", "total_revenue": 88400},
            {"region": "Europe", "total_revenue": 54200},
            {"region": "Asia-Pacific", "total_revenue": 32100}
        ]
    }

@api_app.get("/api/v1/dashboards")
def list_dashboards():
    return [
        {
            "id": 1,
            "name": "Acme Executive Overview",
            "widgets": [
                {"id": 1, "title": "Monthly Revenue Trend", "chart_type": "line"},
                {"id": 2, "title": "Revenue by Category", "chart_type": "bar"},
                {"id": 3, "title": "Acquisition Channels", "chart_type": "pie"},
                {"id": 4, "title": "Price vs. Quantity", "chart_type": "scatter"},
                {"id": 5, "title": "Activity Heatmap", "chart_type": "heatmap"},
                {"id": 6, "title": "Conversion Funnel", "chart_type": "funnel"}
            ]
        }
    ]

@api_app.get("/api/v1/billing")
def get_billing():
    return {
        "plan": "pro",
        "datasets_used": 2,
        "datasets_limit": 20,
        "ai_queries_used": 18,
        "ai_queries_limit": 500
    }

def run_frontend():
    web_dir = os.path.join(os.path.dirname(__file__), "prototype_frontend")
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
    with socketserver.TCPServer(("", 3000), Handler) as httpd:
        print("Frontend running at http://localhost:3000", flush=True)
        httpd.serve_forever()

def run_backend():
    print("Backend running at http://localhost:8000/docs", flush=True)
    uvicorn.run(api_app, host="0.0.0.0", port=8000, log_level="warning")

if __name__ == "__main__":
    t1 = threading.Thread(target=run_frontend, daemon=True)
    t1.start()
    run_backend()

