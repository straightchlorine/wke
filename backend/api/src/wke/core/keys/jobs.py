"""Redis keys of build jobs."""

from __future__ import annotations


def job(job_id: str) -> str:
    """Build the job status key.

    Args:
        job_id: 16 hex char job id.

    Returns:
        str: `job:{id}`.
    """
    return f"job:{job_id}"


def job_heartbeat(job_id: str) -> str:
    """Build the worker heartbeat key.

    `SET ... EX` target, separate from `job:{id}`, so a periodic
    heartbeat write is never a read-modify-write of the full Job and can
    never impact a concurrent pipeline `set_job` (e.g. a status/stage
    change landing between the heartbeat's read and write).

    Args:
        job_id: 16 hex char job id.

    Returns:
        str: `jobhb:{id}`.
    """
    return f"jobhb:{job_id}"


def jobkey(page_id: int, rev_id: int) -> str:
    """Build the single-flight admission key.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.

    Returns:
        str: `jobkey:{page_id}:{rev_id}`.
    """
    return f"jobkey:{page_id}:{rev_id}"


def jobkey_reclaim(page_id: int, rev_id: int) -> str:
    """Build the stale-jobkey reclaim mutex key.

    `JobQueue.admit` holds this only for the moment it takes to reclaim a
    jobkey stuck on a stale done/failed job, so that of N concurrent
    admits racing the same stale jobkey, only one reclaims and enqueues;
    the rest wait for it and return its fresh Job.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.

    Returns:
        str: `jobkey:reclaim:{page_id}:{rev_id}`.
    """
    return f"jobkey:reclaim:{page_id}:{rev_id}"
