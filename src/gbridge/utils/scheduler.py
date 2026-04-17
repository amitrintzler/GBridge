"""Auto-sync scheduler — runs SyncEngine (and, in Phase 2, Pusher) on intervals.

Uses APScheduler in background mode so it runs in a daemon thread and the
tray icon / main thread stays responsive.

Intervals semantics:
- ``sync_interval_minutes > 0`` registers the sync job.
- ``push_interval_minutes > 0`` + non-None ``push_fn`` registers a separate
  push job. Jobs never overlap because both run behind the daemon's single
  lock; APScheduler's ``max_instances=1`` is an extra belt-and-suspenders.
- ``0`` on either side disables that job without breaking the other.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "gbridge-sync"
PUSH_JOB_ID = "gbridge-push"
# Backward-compat alias for existing callers.
JOB_ID = SYNC_JOB_ID


def make_scheduler(
    sync_fn: Callable[[], None],
    interval_minutes: int,
    *,
    push_fn: Callable[[], None] | None = None,
    push_interval_minutes: int = 0,
) -> BackgroundScheduler:
    """Build (but do not start) a scheduler with sync (+ optional push)."""
    scheduler = BackgroundScheduler()
    if interval_minutes > 0:
        scheduler.add_job(
            sync_fn,
            "interval",
            minutes=interval_minutes,
            id=SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Scheduled sync every %d minute(s)", interval_minutes)
    else:
        logger.info("Auto-sync disabled (interval=0)")

    if push_fn is not None and push_interval_minutes > 0:
        scheduler.add_job(
            push_fn,
            "interval",
            minutes=push_interval_minutes,
            id=PUSH_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Scheduled push every %d minute(s)", push_interval_minutes)
    return scheduler
