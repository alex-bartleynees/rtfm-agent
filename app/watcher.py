import asyncio
import logging
import os
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.ai_client import get_ai_client
from app.config import settings
from app.db import get_pg_pool
from app.ingestion.chunker import is_ignored, iter_files
from app.ingestion.pipeline import ingest_file, remove_ingested_documents

logger = logging.getLogger(__name__)


class FileWatcher(FileSystemEventHandler):
    """Watch first, reconcile on startup, and process one file at a time."""

    def __init__(self, directory: str):
        self.directory = Path(os.path.abspath(directory))
        self.loop = asyncio.get_running_loop()
        self.observer = Observer()
        self.pending: dict[Path, tuple[float, int]] = {}
        self.wake = asyncio.Event()
        self.rescan = True
        self.task = None
        self.status = {"state": "starting", "current_file": None, "ingested": 0,
                       "unchanged": 0, "deleted": 0, "failed": 0, "discovered": 0}

    def start(self):
        self.observer.schedule(self, str(self.directory), recursive=True)
        self.observer.start()
        self.task = self.loop.create_task(self.run())
        self.task.add_done_callback(self.worker_finished)
        logger.info("Started file watcher on directory: %s", self.directory)

    def worker_finished(self, task):
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            self.status["state"] = "failed"
            logger.exception("Ingestion worker stopped unexpectedly")

    async def stop(self):
        self.observer.stop()
        await asyncio.to_thread(self.observer.join)
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.status["state"] = "stopped"
        logger.info("Stopped file watcher")

    def on_any_event(self, event):
        if event.event_type not in {"created", "modified", "deleted", "moved"}:
            return
        # Parent-directory modifications accompany ordinary writes; ignore those.
        if event.is_directory and event.event_type == "modified":
            return
        paths = [event.src_path]
        if event.event_type == "moved":
            paths.append(event.dest_path)
        for path in paths:
            self.loop.call_soon_threadsafe(self.enqueue, Path(os.fsdecode(path)), event.is_directory)

    def enqueue(self, path: Path, is_directory: bool = False):
        path = Path(os.path.abspath(path))
        if is_ignored(path, self.directory):
            return
        if is_directory:
            self.rescan = True
        elif path.suffix[1:] in settings.supported_file_types:
            self.pending[path] = (self.loop.time() + 1.0, 0)
        else:
            return
        self.wake.set()

    async def reconcile(self):
        self.status["state"] = "scanning"
        # Complete discovery before cleanup; traversal errors abort deletion.
        files = await asyncio.to_thread(lambda: list(iter_files(self.directory)))
        self.status["discovered"] = len(files)
        pool = get_pg_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute("SELECT source_file FROM ingested_files")
            indexed = await cursor.fetchall()
        indexed_sources = {source for (source,) in indexed}
        for (source,) in indexed:
            path = Path(source)
            absolute = Path(os.path.abspath(path))
            if not absolute.is_relative_to(self.directory):
                continue
            try:
                await asyncio.to_thread(path.stat)
                missing = False
            except FileNotFoundError:
                missing = True
            if missing or is_ignored(absolute, self.directory) or path.suffix[1:] not in settings.supported_file_types:
                await remove_ingested_documents(pool, path)
                self.status["deleted"] += 1
            elif path != absolute:
                # Older runs may have stored paths relative to the working directory.
                if absolute.as_posix() in indexed_sources:
                    await remove_ingested_documents(pool, path)
                else:
                    async with pool.connection() as conn:
                        async with conn.transaction():
                            for table in ("documents", "ingested_files"):
                                await conn.execute(
                                    f"UPDATE {table} SET source_file = %s WHERE source_file = %s",
                                    (absolute.as_posix(), source),
                                )
                    indexed_sources.add(absolute.as_posix())
        for path in files:
            self.pending.setdefault(path, (self.loop.time(), 0))
        logger.info("Reconciled document directory: discovered=%d queued=%d", len(files), len(self.pending))

    async def run(self):
        while True:
            self.wake.clear()
            if self.rescan:
                self.rescan = False
                try:
                    await self.reconcile()
                except Exception:
                    self.status["failed"] += 1
                    logger.exception("Document directory reconciliation failed")
            if not self.pending:
                self.status["state"] = "idle"
                logger.info("Ingestion queue drained: %s", self.status)
                await self.wake.wait()
                continue
            path = min(self.pending, key=lambda item: self.pending[item][0])
            deadline, attempt = self.pending[path]
            delay = deadline - self.loop.time()
            if delay > 0:
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
                continue
            del self.pending[path]
            self.status.update(state="ingesting", current_file=str(path))
            try:
                try:
                    await asyncio.to_thread(path.stat)
                except FileNotFoundError:
                    await remove_ingested_documents(get_pg_pool(), path)
                    self.status["deleted"] += 1
                else:
                    changed = await ingest_file(path, get_ai_client(), get_pg_pool())
                    self.status["ingested" if changed else "unchanged"] += 1
            except Exception:
                logger.exception("File ingestion failed: %s attempt=%d", path, attempt + 1)
                if attempt < 2:
                    self.pending.setdefault(path, (self.loop.time() + 2 ** (attempt + 1), attempt + 1))
                else:
                    self.status["failed"] += 1
            finally:
                self.status["current_file"] = None


def start_file_watcher():
    watcher = FileWatcher(settings.docs_dir)
    watcher.start()
    return watcher


async def stop_file_watcher(watcher: FileWatcher):
    await watcher.stop()
