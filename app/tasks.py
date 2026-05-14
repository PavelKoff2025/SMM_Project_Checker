"""Module entry-point for RQ workers.

The worker process imports `app.tasks.run_check_job` by dotted path and
invokes it with the check id. We lazily build the Flask app on first call,
which gives us a proper app context for SQLAlchemy and configuration.
"""

from __future__ import annotations

import os

_app = None


def _get_app():
    global _app
    if _app is None:
        from app import create_app
        _app = create_app(os.environ.get('FLASK_ENV', 'production'))
    return _app


def run_check_job(check_id: int) -> None:
    from app.services.check_service import run_check
    run_check(_get_app(), check_id)
