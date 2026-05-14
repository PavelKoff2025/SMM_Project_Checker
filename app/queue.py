"""Background task queue powered by RQ + Redis.

Falls back to a daemon thread when Redis is not configured so local
development without Docker keeps working transparently.
"""

from __future__ import annotations

import logging
import threading

from flask import Flask, current_app

logger = logging.getLogger(__name__)

_redis_client = None
_queue = None
_initialised = False


def init_queue(app: Flask) -> None:
    """Best-effort initialization. Failures are logged, not raised."""
    global _redis_client, _queue, _initialised
    _initialised = True
    url = app.config.get('REDIS_URL') or ''
    if not url:
        logger.info('REDIS_URL is not set; using in-process thread executor.')
        return
    try:
        from redis import Redis
        from rq import Queue
        _redis_client = Redis.from_url(url)
        _redis_client.ping()
        _queue = Queue('checks', connection=_redis_client, default_timeout=600)
        logger.info('RQ queue connected to %s', url)
    except Exception:
        logger.exception('Failed to initialize RQ; falling back to threads.')
        _redis_client = None
        _queue = None


def get_queue():
    return _queue


def get_redis():
    return _redis_client


def enqueue_check(check_id: int) -> None:
    """Enqueue a check for background processing.

    If RQ is available, the worker imports the job by dotted path; otherwise
    a daemon thread runs the check inside the current app's context.
    """
    app = current_app._get_current_object()
    if _queue is not None:
        _queue.enqueue(
            'app.tasks.run_check_job',
            check_id,
            job_id=f'check-{check_id}',
            result_ttl=3600,
            failure_ttl=86400,
        )
        return

    from app.services.check_service import run_check
    threading.Thread(
        target=run_check, args=(app, check_id), daemon=True
    ).start()
