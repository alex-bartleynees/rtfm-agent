import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.ingestion.chunker import is_ignored, iter_files
from app.watcher import FileWatcher
from watchdog.events import FileMovedEvent


def test_ignore_patterns_prune_directories_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "docs_ignore_patterns", [".obsidian", "*.tmp", "private/*", "secret.md"])
    for name in [".obsidian/config.md", "private/nested/doc.md", "nested/secret.md", "nested/keep.md"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("hello")
    assert list(iter_files(tmp_path)) == [tmp_path / "nested/keep.md"]
    assert is_ignored(tmp_path / "nested/file.tmp", tmp_path)
    assert is_ignored(tmp_path.parent / "outside.md", tmp_path)


async def test_queue_coalesces_and_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "docs_ignore_patterns", ["ignore.md"])
    watcher = FileWatcher(str(tmp_path))
    watcher.enqueue(tmp_path / "keep.md")
    watcher.enqueue(tmp_path / "keep.md")
    watcher.enqueue(tmp_path / "ignore.md")
    watcher.enqueue(tmp_path / "image.png")
    assert list(watcher.pending) == [tmp_path / "keep.md"]


async def test_change_during_ingestion_gets_one_followup(tmp_path, monkeypatch):
    path = tmp_path / "keep.md"
    path.write_text("hello")
    watcher = FileWatcher(str(tmp_path))
    watcher.rescan = False
    watcher.pending[path] = (0, 0)
    finished = asyncio.Event()
    calls = 0

    async def ingest(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            watcher.enqueue(path)
            watcher.enqueue(path)
            watcher.pending[path] = (0, 0)
        else:
            finished.set()
        return True

    monkeypatch.setattr("app.watcher.get_pg_pool", lambda: object())
    monkeypatch.setattr("app.watcher.get_ai_client", lambda: object())
    monkeypatch.setattr("app.watcher.ingest_file", ingest)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.wait_for(finished.wait(), 2)
        assert calls == 2
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_failed_scan_does_not_delete_records(tmp_path, monkeypatch):
    watcher = FileWatcher(str(tmp_path / "missing"))
    remove = AsyncMock()
    monkeypatch.setattr("app.watcher.remove_ingested_documents", remove)
    with pytest.raises(FileNotFoundError):
        await watcher.reconcile()
    remove.assert_not_called()


async def test_startup_queues_existing_files_and_cleans_missing_or_ignored(tmp_path, monkeypatch):
    keep = tmp_path / "keep.md"
    keep.write_text("hello")
    ignored = tmp_path / "ignore.md"
    ignored.write_text("ignore")
    missing = tmp_path / "missing.md"
    outside = tmp_path.parent / "outside.md"
    monkeypatch.setattr(settings, "docs_ignore_patterns", ["ignore.md"])
    cursor = AsyncMock()
    cursor.fetchall.return_value = [(str(p),) for p in (keep, ignored, missing, outside)]
    conn = AsyncMock()
    conn.execute.return_value = cursor
    pool = MagicMock()
    pool.connection.return_value.__aenter__.return_value = conn
    remove = AsyncMock()
    monkeypatch.setattr("app.watcher.get_pg_pool", lambda: pool)
    monkeypatch.setattr("app.watcher.remove_ingested_documents", remove)
    watcher = FileWatcher(str(tmp_path))
    await watcher.reconcile()
    assert list(watcher.pending) == [keep]
    assert {call.args[1] for call in remove.await_args_list} == {ignored, missing}


async def test_move_queues_both_paths(tmp_path):
    watcher = FileWatcher(str(tmp_path))
    old, new = tmp_path / "old.md", tmp_path / "new.md"
    watcher.on_any_event(FileMovedEvent(str(old), str(new)))
    await asyncio.sleep(0)
    assert set(watcher.pending) == {old, new}


async def test_failed_file_is_retried_later(tmp_path, monkeypatch):
    path = tmp_path / "file.md"
    path.write_text("hello")
    watcher = FileWatcher(str(tmp_path))
    watcher.rescan = False
    watcher.pending[path] = (0, 0)
    attempted = asyncio.Event()

    async def fail(*args):
        attempted.set()
        raise RuntimeError("failure")

    monkeypatch.setattr("app.watcher.get_pg_pool", lambda: object())
    monkeypatch.setattr("app.watcher.get_ai_client", lambda: object())
    monkeypatch.setattr("app.watcher.ingest_file", fail)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.wait_for(attempted.wait(), 2)
        deadline, attempt = watcher.pending[path]
        assert attempt == 1
        assert deadline > watcher.loop.time()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_worker_continues_after_file_failure(tmp_path, monkeypatch):
    first, second = tmp_path / "first.md", tmp_path / "second.md"
    first.write_text("first")
    second.write_text("second")
    watcher = FileWatcher(str(tmp_path))
    watcher.rescan = False
    watcher.pending = {first: (0, 2), second: (0, 0)}
    finished = asyncio.Event()

    async def ingest(path, *args):
        if path == first:
            raise RuntimeError("embedding failure")
        finished.set()
        return True

    monkeypatch.setattr("app.watcher.get_pg_pool", lambda: object())
    monkeypatch.setattr("app.watcher.get_ai_client", lambda: object())
    monkeypatch.setattr("app.watcher.ingest_file", ingest)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.wait_for(finished.wait(), 2)
        assert watcher.status["failed"] == 1
        assert watcher.status["ingested"] == 1
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
