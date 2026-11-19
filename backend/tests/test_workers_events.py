import asyncio
import json

from app.services import events
from app.workers import tasks
from tests.conftest import set_plan, upload


def test_worker_jobs_run(client, owner):
    set_plan(client, owner, "pro")
    upload(client, owner)
    assert asyncio.run(tasks.poll_due_connectors({})) == 0
    assert asyncio.run(tasks.rescan_anomalies({})) == 1
    assert asyncio.run(tasks.send_scheduled_reports({})) == 0


def test_events_roundtrip():
    async def run():
        gen = events.subscribe(42)
        first = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.3)
        events.publish(42, "ingest.completed", rows=5)
        chunk = await asyncio.wait_for(first, 5)
        await gen.aclose()
        return chunk

    chunk = asyncio.run(run())
    assert chunk.startswith("data: ")
    assert json.loads(chunk[6:]) == {"type": "ingest.completed", "rows": 5}
