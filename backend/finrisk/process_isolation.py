"""Killable multiprocessing boundary used by document workloads."""

from __future__ import annotations

import asyncio
import math
import multiprocessing
import os
import pickle
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


class WorkerTimeoutError(TimeoutError):
    """The child process did not publish a result before its budget expired."""


MAX_WORKER_RESULT_BYTES = 128 * 1024 * 1024


class _BoundedResultWriter:
    def __init__(self, handle):
        self.handle = handle

    def write(self, data):
        if self.handle.tell() + memoryview(data).nbytes > MAX_WORKER_RESULT_BYTES:
            raise ValueError("document worker result exceeds size limit")
        return self.handle.write(data)


class _AtomicResult:
    """Queue-compatible single-result writer, private to a trusted local worker.

    A Queue timeout only covers pipe readiness: once a frame starts, its receive
    can block forever if the child stalls mid-frame. Publish a complete file by
    atomic rename instead. The parent never reads a partially written result.
    """

    def __init__(self, path: str):
        self.path = Path(path)

    def put(self, value: Any) -> None:
        partial = self.path.with_suffix(".partial")
        with partial.open("xb") as handle:
            # Same trusted Python-object contract as multiprocessing.Queue. This
            # is not a decoder for uploaded documents or persisted user artifacts.
            pickle.dump(value, _BoundedResultWriter(handle), protocol=pickle.HIGHEST_PROTOCOL)
            if handle.tell() > MAX_WORKER_RESULT_BYTES:
                raise ValueError("document worker result exceeds size limit")
        os.replace(partial, self.path)


def _run_to_file(target: Callable, args: tuple[Any, ...], path: str) -> None:
    target(_AtomicResult(path), *args)


async def _join(process: multiprocessing.Process, timeout: float) -> None:
    await asyncio.to_thread(process.join, timeout)


async def _terminate(process: multiprocessing.Process, timeout: float) -> None:
    if process.is_alive():
        process.terminate()
    await _join(process, timeout)
    if process.is_alive():
        process.kill()
        await _join(process, timeout)
    if process.is_alive():
        raise RuntimeError("document worker could not be reclaimed")


async def run_spawned_worker(
    target: Callable[..., None],
    args: tuple[Any, ...],
    *,
    timeout: float,
    join_timeout: float = 5,
) -> tuple[str, Any]:
    """Run one queue-reporting worker and deterministically reclaim its process.

    Workers retain their ``(queue, *args)`` / ``queue.put`` contract and publish
    exactly one ``(status, payload)`` tuple in a private, atomically published file.
    """
    if any(type(value) not in {int, float} or not math.isfinite(value) or value <= 0
           for value in (timeout, join_timeout)):
        raise ValueError("worker time budgets must be finite positive numbers")
    context = multiprocessing.get_context("spawn")
    temporary = TemporaryDirectory(prefix="finrisk-worker-")
    result_path = Path(temporary.name) / "result"
    process = context.Process(
        target=_run_to_file,
        args=(target, args, str(result_path)),
        daemon=True,
    )
    try:
        process.start()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkerTimeoutError
            if result_path.exists():
                if result_path.stat().st_size > MAX_WORKER_RESULT_BYTES:
                    raise RuntimeError("document worker result exceeds size limit")
                with result_path.open("rb") as handle:
                    result = pickle.load(handle)  # trusted child, private temporary directory
                if not isinstance(result, tuple) or len(result) != 2:
                    raise RuntimeError("document worker returned an invalid result")
                break
            if not process.is_alive():
                # Check once more after observing exit, in case publication raced
                # the earlier exists() check.
                if result_path.exists():
                    continue
                raise RuntimeError("document worker exited without a result")
            await asyncio.sleep(min(remaining, 0.01))

        await _join(process, join_timeout)
        if process.is_alive():
            await _terminate(process, join_timeout)
        return result
    finally:
        async def reclaim():
            if process.is_alive():
                await _terminate(process, join_timeout)
            process.close()
            temporary.cleanup()

        # A second cancellation during SIGTERM/join must not strand a child or
        # its private result files. Shield a strongly referenced cleanup task,
        # await it to completion, then preserve the caller's cancellation.
        cleanup = asyncio.create_task(reclaim())
        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        cleanup.result()
        if cancelled:
            raise asyncio.CancelledError
