"""RQ worker entrypoint. Run with `python worker.py`."""

import os

from redis import Redis
from rq import Worker


def main() -> None:
    redis_url = os.environ['REDIS_URL']
    queues = os.environ.get('RQ_QUEUES', 'checks').split(',')
    connection = Redis.from_url(redis_url)
    worker = Worker(queues, connection=connection)
    worker.work(with_scheduler=False)


if __name__ == '__main__':
    main()
