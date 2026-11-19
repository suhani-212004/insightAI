from app.services import ai_query
from app.services.ai_query import AIAnswer, ChartOut, _infer_chart
from tests.conftest import set_plan, upload


class FakeGen:
    """Stands in for OpenAI. Returns queued answers and records what it was sent."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def generate(self, question, schema, history, error=None):
        self.calls.append({"question": question, "schema": schema, "history": history, "error": error})
        return self.answers.pop(0)


def test_ask_returns_rows_and_chart(client, owner):
    upload(client, owner)
    gen = FakeGen(AIAnswer(sql="SELECT region, sum(revenue) AS revenue FROM sales GROUP BY 1 ORDER BY 1",
                           chart=ChartOut(type="bar", x="region", y=["revenue"]),
                           explanation="Revenue by region."))
    ai_query.set_generator(gen)

    r = client.post("/api/v1/ai/ask", headers=owner, json={"question": "Revenue by region?"})
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    assert msg["chart"]["type"] == "bar" and len(msg["rows"]) == 3
    assert "TABLE sales" in gen.calls[0]["schema"] and "sample:" in gen.calls[0]["schema"]


def test_conversation_memory_is_passed_back(client, owner):
    upload(client, owner)
    gen = FakeGen(
        AIAnswer(sql="SELECT region, sum(revenue) AS revenue FROM sales GROUP BY 1", explanation="first"),
        AIAnswer(sql="SELECT region, sum(revenue) AS revenue FROM sales WHERE region='North' GROUP BY 1",
                 explanation="filtered"),
    )
    ai_query.set_generator(gen)
    sid = client.post("/api/v1/ai/ask", headers=owner, json={"question": "revenue by region"}).json()["session_id"]
    client.post("/api/v1/ai/ask", headers=owner, json={"question": "only North", "session_id": sid})

    history = gen.calls[1]["history"]
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert "GROUP BY" in history[1]["sql"]

    msgs = client.get(f"/api/v1/ai/sessions/{sid}", headers=owner).json()
    assert len(msgs) == 4
    assert len(client.get("/api/v1/ai/sessions", headers=owner).json()) == 1


def test_bad_sql_is_retried_with_error(client, owner):
    upload(client, owner)
    gen = FakeGen(
        AIAnswer(sql="SELECT revnue FROM sales", explanation="oops"),
        AIAnswer(sql="SELECT sum(revenue) AS total FROM sales", explanation="fixed"),
    )
    ai_query.set_generator(gen)
    msg = client.post("/api/v1/ai/ask", headers=owner, json={"question": "total"}).json()["message"]
    assert msg["content"] == "fixed" and msg["rows"] == [{"total": sum(100 + i for i in range(30))}]
    assert "revnue" in gen.calls[1]["error"]


def test_unsafe_sql_from_llm_never_runs(client, owner):
    upload(client, owner)
    gen = FakeGen(AIAnswer(sql="DROP TABLE sales", explanation="x"), AIAnswer(sql="DELETE FROM sales", explanation="y"))
    ai_query.set_generator(gen)
    msg = client.post("/api/v1/ai/ask", headers=owner, json={"question": "drop it"}).json()["message"]
    assert msg["rows"] is None and "couldn't run" in msg["content"]
    assert client.post("/api/v1/query", headers=owner, json={"sql": "SELECT count(*) AS n FROM sales"}).json()[
        "rows"] == [{"n": 30}]


def test_unanswerable(client, owner):
    ai_query.set_generator(FakeGen(AIAnswer(sql=None, explanation="No weather data available.")))
    msg = client.post("/api/v1/ai/ask", headers=owner, json={"question": "weather?"}).json()["message"]
    assert msg["sql"] is None and "weather" in msg["content"]


def test_no_key_fallback(client, owner):
    upload(client, owner)
    msg = client.post("/api/v1/ai/ask", headers=owner, json={"question": "anything"}).json()["message"]
    assert "OPENAI_API_KEY" in msg["content"] and len(msg["rows"]) == 20


def test_daily_ai_limit(client, owner):
    ai_query.set_generator(FakeGen(*[AIAnswer(sql=None, explanation="-") for _ in range(30)]))
    for _ in range(25):
        assert client.post("/api/v1/ai/ask", headers=owner, json={"question": "hi"}).status_code == 200
    assert client.post("/api/v1/ai/ask", headers=owner, json={"question": "hi"}).status_code == 402
    set_plan(client, owner, "pro")
    assert client.post("/api/v1/ai/ask", headers=owner, json={"question": "hi"}).status_code == 200


def test_unknown_session(client, owner):
    assert client.post("/api/v1/ai/ask", headers=owner, json={"question": "hi", "session_id": 999}).status_code == 404
    assert client.get("/api/v1/ai/sessions/999", headers=owner).status_code == 404
    assert client.delete("/api/v1/ai/sessions/999", headers=owner).status_code == 404


def test_infer_chart_fixes_bad_axes():
    rows = [{"m": "2026-01", "rev": 10, "cnt": 2}]
    spec = _infer_chart(ChartOut(type="line", x="month", y=["revenue"]), ["m", "rev", "cnt"], rows)
    assert spec["x"] == "m" and spec["y"] == ["rev", "cnt"]
    spec = _infer_chart(ChartOut(type="bar"), ["name"], [{"name": "a"}])
    assert spec["type"] == "table"
    spec = _infer_chart(ChartOut(type="heatmap", x="a", y=["b"]), ["a", "b", "v"], [{"a": "x", "b": "y", "v": 1}])
    assert spec["value"] == "v"
