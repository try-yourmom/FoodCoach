from __future__ import annotations

import logging

from redis import Redis
from rq import Queue, Worker

from app.config import settings
from app.db import init_db
from app.jobs import recover_pending_jobs


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.queue_name, connection=connection)
    recovered = recover_pending_jobs(queue)
    logging.info('Recovered %s pending assessment jobs', recovered)
    Worker([queue], connection=connection).work()


if __name__ == '__main__':
    main()