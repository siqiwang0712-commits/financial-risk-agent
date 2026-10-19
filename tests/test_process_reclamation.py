import asyncio
import os
import signal
import time
from pathlib import Path

import pytest
from finrisk.process_isolation import WorkerTimeoutError, run_spawned_worker
from finrisk.runtime import document_limits


def stubborn_worker(queue, pid_file):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(pid_file).write_text(str(os.getpid()))
    time.sleep(30)


def successful_worker(queue):
    queue.put(("ok", {"value": 42}))


def exiting_worker(queue):
    return


def partially_publishing_worker(queue, pid_file):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(pid_file).write_text(str(os.getpid()))
    # Simulate serialization stalled after publishing only part of a result.
    queue.path.with_suffix(".partial").write_bytes(b"incomplete pickle frame")
    time.sleep(30)


def large_result_worker(queue):
    queue.put(("ok", b"x" * (2 * 1024 * 1024)))


def assert_reclaimed(pid_file):
    assert pid_file.exists(), "worker must start before testing reclamation"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM-ignore control is POSIX-specific")
def test_timeout_kills_and_reaps_worker_ignoring_sigterm(tmp_path):
    pid_file = tmp_path / "worker.pid"
    with pytest.raises(WorkerTimeoutError):
        asyncio.run(run_spawned_worker(stubborn_worker, (str(pid_file),), timeout=1, join_timeout=0.1))
    assert_reclaimed(pid_file)


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM-ignore control is POSIX-specific")
def test_request_cancellation_reclaims_worker(tmp_path):
    pid_file = tmp_path / "worker.pid"

    async def cancel():
        task = asyncio.create_task(run_spawned_worker(
            stubborn_worker, (str(pid_file),), timeout=30, join_timeout=0.1,
        ))
        for _ in range(200):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    started = time.monotonic()
    asyncio.run(cancel())
    assert time.monotonic() - started < 5
    assert_reclaimed(pid_file)


def test_worker_success_and_early_failure():
    assert asyncio.run(run_spawned_worker(successful_worker, (), timeout=5)) == ("ok", {"value": 42})
    with pytest.raises(RuntimeError, match="without a result"):
        asyncio.run(run_spawned_worker(exiting_worker, (), timeout=5))


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM-ignore control is POSIX-specific")
def test_partial_result_cannot_block_timeout_or_executor_shutdown(tmp_path):
    pid_file = tmp_path / "worker.pid"
    started = time.monotonic()
    with pytest.raises(WorkerTimeoutError):
        asyncio.run(run_spawned_worker(
            partially_publishing_worker, (str(pid_file),), timeout=1, join_timeout=0.1,
        ))
    assert time.monotonic() - started < 5
    assert_reclaimed(pid_file)


def test_large_result_does_not_deadlock_on_pipe_capacity():
    status, result = asyncio.run(run_spawned_worker(large_result_worker, (), timeout=5))
    assert status == "ok" and len(result) == 2 * 1024 * 1024


@pytest.mark.parametrize("timeout", ["nan", "inf", "-inf"])
def test_document_time_budget_must_be_finite(monkeypatch, timeout):
    monkeypatch.setenv("FINRISK_ANALYSIS_TIMEOUT_SECONDS", timeout)
    with pytest.raises(RuntimeError, match="positive"):
        document_limits()


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM-ignore control is POSIX-specific")
def test_repeated_cancellation_cannot_interrupt_reclamation(tmp_path, monkeypatch):
    from finrisk import process_isolation
    pid_file = tmp_path / 'worker.pid'
    original = process_isolation._terminate
    entered = asyncio.Event()

    async def slow_cleanup(process, timeout):
        entered.set()
        await asyncio.sleep(0.05)
        await original(process, timeout)

    monkeypatch.setattr(process_isolation, '_terminate', slow_cleanup)

    async def cancel_twice():
        task = asyncio.create_task(run_spawned_worker(
            stubborn_worker, (str(pid_file),), timeout=30, join_timeout=0.1,
        ))
        for _ in range(200):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        task.cancel()
        await entered.wait()
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
            assert_reclaimed(pid_file)
        finally:
            # Keep the regression itself from leaking the vulnerable worker.
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    asyncio.run(cancel_twice())


@pytest.mark.parametrize('budget', [float('nan'), float('inf'), 0, -1, True])
@pytest.mark.parametrize('name', ['timeout', 'join_timeout'])
def test_worker_rejects_invalid_budgets_before_spawning(budget, name):
    arguments = {'timeout': 5, 'join_timeout': 0.1, name: budget}
    with pytest.raises(ValueError, match='finite positive'):
        asyncio.run(run_spawned_worker(successful_worker, (), **arguments))


def test_result_size_limit_precedes_disk_write(tmp_path, monkeypatch):
    from finrisk import process_isolation
    monkeypatch.setattr(process_isolation, 'MAX_WORKER_RESULT_BYTES', 64)
    result = tmp_path / 'result'
    writer = process_isolation._AtomicResult(str(result))
    with pytest.raises(ValueError, match='size limit'):
        writer.put(('ok', b'x'*1000))
    assert not result.exists()
    assert result.with_suffix('.partial').stat().st_size <= 64
