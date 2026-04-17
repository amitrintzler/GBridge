"""Tests for the auto-sync scheduler helper."""

from __future__ import annotations

from gbridge.utils.scheduler import (
    JOB_ID,
    PUSH_JOB_ID,
    SYNC_JOB_ID,
    make_scheduler,
)


class TestMakeScheduler:
    def test_registers_job_when_interval_positive(self) -> None:
        sched = make_scheduler(lambda: None, interval_minutes=5)
        try:
            job = sched.get_job(JOB_ID)
            assert job is not None
            # Interval in seconds = 300
            assert job.trigger.interval.total_seconds() == 300
        finally:
            if sched.running:
                sched.shutdown(wait=False)

    def test_no_job_when_interval_zero(self) -> None:
        sched = make_scheduler(lambda: None, interval_minutes=0)
        try:
            assert sched.get_job(JOB_ID) is None
        finally:
            if sched.running:
                sched.shutdown(wait=False)

    def test_push_job_registered_when_push_fn_given(self) -> None:
        sched = make_scheduler(
            lambda: None,
            interval_minutes=5,
            push_fn=lambda: None,
            push_interval_minutes=10,
        )
        try:
            assert sched.get_job(SYNC_JOB_ID) is not None
            push = sched.get_job(PUSH_JOB_ID)
            assert push is not None
            assert push.trigger.interval.total_seconds() == 600
        finally:
            if sched.running:
                sched.shutdown(wait=False)

    def test_no_push_job_when_interval_zero(self) -> None:
        sched = make_scheduler(
            lambda: None,
            interval_minutes=5,
            push_fn=lambda: None,
            push_interval_minutes=0,
        )
        try:
            assert sched.get_job(PUSH_JOB_ID) is None
        finally:
            if sched.running:
                sched.shutdown(wait=False)
