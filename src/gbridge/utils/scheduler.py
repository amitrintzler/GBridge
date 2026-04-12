"""Auto-sync scheduler — run SyncEngine every N minutes.

Uses APScheduler in background mode so it runs in a daemon thread and
the tray icon / main thread stays responsive.  A sync interval of
0 disables scheduling entirely — the job is simply never registered.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

JOB_ID = "gbridge-sync"


def make_scheduler(
    sync_fn: Callable[[], None], interval_minutes: int
) -> BackgroundScheduler:
    """Build (but do not start) a scheduler that calls ``sync_fn`` periodically.

    Caller is responsible for starting and shutting it down — this keeps
    tests and the tray loop easy to reason about.
    """
    scheduler = BackgroundScheduler()
    if interval_minutes > 0:
        scheduler.add_job(
            sync_fn,
            "interval",
            minutes=interval_minutes,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,  # never overlap sync runs
            coalesce=True,
        )
        logger.info("Scheduled sync every %d minute(s)", interval_minutes)
    else:
        logger.info("Auto-sync disabled (interval=0)")
    return scheduler
