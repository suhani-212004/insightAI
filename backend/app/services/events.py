"""Real-time events over Redis pub/sub, streamed to browsers with SSE.

publish()  - called from API routes and background workers (sync).
subscribe() - async generator used by the SSE endpoint.

Channel per org: `org:<id>:events`. Messages are JSON: {"type": ..., ...}.
If Redis is down, publishing silently does nothing so uploads still work.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator

import redis
import redis.asyncio as aioredis

from app.core.config import settings

log = logging.getLogger(__name__)
_sync_client: redis.Redis | None = None


def channel(org_id: int) -> str:
    return f"org:{int(org_id)}:events"


def publish(org_id: int, event_type: str, **data) -> None:
    global _sync_client
    try:
        if _sync_client is None:
            _sync_client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        _sync_client.publish(channel(org_id), json.dumps({"type": event_type, **data}, default=str))
    except redis.RedisError as e:  # never break a request because of events
        log.warning("event publish failed: %s", e)


async def subscribe(org_id: int) -> AsyncIterator[str]:
    client = aioredis.Redis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(org_id))
    loop = asyncio.get_running_loop()
    last_sent = loop.time()
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                if loop.time() - last_sent > 15:
                    last_sent = loop.time()
                    yield ": keep-alive\n\n"  # SSE comment, keeps proxies from closing the stream
                continue
            last_sent = loop.time()
            data = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
            yield f"data: {data}\n\n"
    finally:
        await pubsub.unsubscribe(channel(org_id))
        await pubsub.aclose()
        await client.aclose()
