"""Killable multiprocessing boundary used by document workloads."""

from __future__ import annotations

import asyncio
import multiprocessing
import queue as queue_module
from collections.abc import Callable
from typing import Any


class WorkerTimeoutError(TimeoutError):
    """The child process did not publish a result before its budget expired."""


async def _join(process: multiprocessing.Process, timeout: float) -> None:
    await asyncio.to_thread(process.join, timeout)


async def _terminate(process: multiprocessing.Process, timeout: float) -> None:
    if process.is_alive():
        process.terminate()
    await _join(process, timeout)


async def run_spawned_worker(
    target: Callable[..., None],
    args: tuple[Any, ...],
    *,
    timeout: float,
    join_timeout: float = 5,
) -> tuple[str, Any]:
    """Run one queue-reporting worker and deterministically reclaim its process.

    Workers use the existing ``(queue, *args)`` contract and publish exactly one
    ``(status, payload)`` tuple.  Reading happens while the child is alive so a
    large payload cannot deadlock on a full multiprocessing pipe.
    """
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=target,
        args=(result_queue, *args),
        daemon=True,
    )
    try:
        process.start()
        try:
            result = await asyncio.to_thread(result_queue.get, True, timeout)
        except queue_module.Empty as exc:
            await _terminate(process, join_timeout)
            raise WorkerTimeoutError from exc

        await _join(process, join_timeout)
        if process.is_alive():
            await _terminate(process, join_timeout)
        return result
    finally:
        if process.is_alive():
            await _terminate(process, join_timeout)
        result_queue.close()
        await asyncio.to_thread(result_queue.join_thread)
