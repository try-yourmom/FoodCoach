from __future__ import annotations

from functools import lru_cache

from redis import Redis
from rq import Queue

from app.config import settings
from app.jobs import process_assessment


@lru_cache(maxsize=1)
def get_redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


@lru_cache(maxsize=1)
def get_queue() -> Queue:
    return Queue(settings.queue_name, connection=get_redis_connection())


def enqueue_assessment(assessment_id: str):
    return get_queue().enqueue(
        process_assessment,
        assessment_id,
        job_id=assessment_id,
        job_timeout=settings.job_timeout_seconds,
    )