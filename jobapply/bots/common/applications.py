"""CSV application logging compatible with the backend applications store."""

from __future__ import annotations

import csv
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .paths import APP_ROOT, resolve_app_path
from .results import JobInfo


APPLICATION_HEADERS = (
    "id",
    "timestamp",
    "platform",
    "jobTitle",
    "company",
    "location",
    "jobUrl",
    "status",
    "appliedAt",
    "notes",
)

_locks_guard = threading.Lock()
_locks: dict[Path, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _locks_guard:
        return _locks.setdefault(resolved, threading.RLock())


@contextmanager
def _process_lock(path: Path):
    """Use a short-lived sidecar lock so concurrent bot processes cannot race."""

    lock_path = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + 15
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 120:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for applications CSV lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


class ApplicationCsvLogger:
    def __init__(self, path: Path | str) -> None:
        self.path = resolve_app_path(str(path), "logs/applications.csv", app_root=APP_ROOT)
        self._lock = _lock_for(self.path)
        self.ensure_header()

    def ensure_header(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with _process_lock(self.path):
                self._ensure_header_unlocked()

    def _ensure_header_unlocked(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(APPLICATION_HEADERS)
            return

        try:
            with self.path.open("r", newline="", encoding="utf-8-sig") as handle:
                first_row = next(csv.reader(handle), [])
        except (OSError, csv.Error) as error:
            raise RuntimeError(f"Cannot validate applications CSV {self.path}: {error}") from error
        if tuple(first_row) == APPLICATION_HEADERS:
            return

        existing = self.path.read_text(encoding="utf-8-sig")
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(APPLICATION_HEADERS)
            handle.write(existing)
            if existing and not existing.endswith(("\n", "\r")):
                handle.write("\n")
        os.replace(temporary, self.path)

    def log(
        self,
        platform: str,
        job: JobInfo,
        status: str,
        notes: str = "",
    ) -> dict[str, str]:
        if status not in {"applied", "skipped", "failed"}:
            raise ValueError(f"Invalid application status: {status}")
        normalized = job.normalized()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        row = {
            "id": f"{platform}-{uuid.uuid4().hex}",
            "timestamp": timestamp,
            "platform": platform,
            "jobTitle": normalized.title,
            "company": normalized.company,
            "location": normalized.location,
            "jobUrl": normalized.url,
            "status": status,
            "appliedAt": timestamp if status == "applied" else "",
            "notes": (notes or "").strip(),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with _process_lock(self.path):
                self._ensure_header_unlocked()
                with self.path.open("a+", newline="", encoding="utf-8") as handle:
                    handle.seek(0, os.SEEK_END)
                    end = handle.tell()
                    if end:
                        handle.seek(end - 1)
                        if handle.read(1) not in {"\n", "\r"}:
                            handle.seek(0, os.SEEK_END)
                            handle.write("\n")
                    handle.seek(0, os.SEEK_END)
                    csv.writer(handle).writerow([row[header] for header in APPLICATION_HEADERS])
                    handle.flush()
                    os.fsync(handle.fileno())
        return row
