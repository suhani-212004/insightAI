"""Check that the configured LLM provider is reachable and returns usable SQL.

Run from backend/:   python -m app.check_llm
Exit code 0 = working, 1 = not working. Never prints the API key.
"""
import sys
import time

from app.services.ai_query import LLMUnavailable, NoKeyGenerator, build_generator

SAMPLE_SCHEMA = (
    "TABLE sales (order_date timestamp, region text, revenue numeric, units integer)  -- sales, 30 rows\n"
    '  sample: {"order_date": "2026-01-11", "region": "North", "revenue": "100", "units": "1"}'
)


def main() -> int:
    gen = build_generator()
    if isinstance(gen, NoKeyGenerator):
        print("No LLM key configured. Set GROQ_API_KEY or OPENAI_API_KEY in backend/.env")
        return 1
    print(f"Provider: {gen.provider}  Model: {gen.model}")
    start = time.time()
    try:
        answer = gen.generate("What is total revenue by region?", SAMPLE_SCHEMA, [])
    except LLMUnavailable as e:
        msg = str(e)
        if "401" in msg or "invalid_api_key" in msg:
            print("FAILED: the provider rejected the API key. Check it was copied in full.")
        elif "429" in msg:
            print("FAILED: rate limited by the provider. Wait a minute and retry.")
        else:
            print(f"FAILED: {msg[:300]}")
        return 1
    print(f"OK in {time.time() - start:.1f}s")
    print(f"  SQL:   {answer.sql}")
    print(f"  Chart: {answer.chart.type} x={answer.chart.x} y={answer.chart.y}")
    print(f"  Text:  {answer.explanation}")
    return 0 if answer.sql else 1


if __name__ == "__main__":
    sys.exit(main())
