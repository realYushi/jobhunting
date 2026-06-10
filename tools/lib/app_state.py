"""ApplicationState — single-owner interface for the application tracker.

Wraps tracker.py's load/save/upsert primitives behind a class so callers
(workflow, reconcile, pipeline) share one load → N mutations → one save
cycle rather than each loading and saving independently.

tracker.py internals (load_tracker, save_tracker, migration logic) are
unchanged.  ApplicationState is the interface callers use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .tracker import (
    ApplicationRecord,
    JobKey,
    load_keyset,
    load_tracker,
    save_tracker,
    store_keyset,
    upsert_active_application,
)


class ApplicationState:
    """Owner of the in-memory tracker dict and its on-disk path.

    Load once, mutate via named operations, save once.  The raw dict is
    accessible via ``.tracker`` for callers (dedup index builders, reconcile
    status mutations) that need it directly.
    """

    def __init__(self, path: Path, tracker: dict[str, Any]) -> None:
        self._path = path
        self._tracker = tracker

    @classmethod
    def load(cls, path: Path) -> "ApplicationState":
        """Load tracker from ``path``, creating an in-memory default when missing."""
        return cls(path, load_tracker(path))

    @property
    def tracker(self) -> dict[str, Any]:
        """The raw tracker dict. Mutate directly for one-off status changes."""
        return self._tracker

    @property
    def path(self) -> Path:
        """The on-disk path this state will be saved to."""
        return self._path

    def save(self) -> None:
        """Persist the tracker to disk (no-op when content is byte-identical)."""
        save_tracker(self._path, self._tracker)

    def upsert_active(self, record: ApplicationRecord) -> None:
        """Insert or replace one active application (dedup by key)."""
        upsert_active_application(self._tracker, record)

    def keyset(self, field: str) -> set[JobKey]:
        """Materialise the flat key list at tracker[field] as a set[JobKey]."""
        return load_keyset(self._tracker, field)

    def store_keyset(self, field: str, keys: set[JobKey]) -> None:
        """Persist a set[JobKey] back to tracker[field] as a list of dicts."""
        store_keyset(self._tracker, field, keys)

    def iter_applications(
        self, buckets: tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Return a flat list of application dicts from the requested buckets.

        When ``buckets`` is None, all buckets are returned.
        """
        apps = self._tracker.get("applications", {})
        if buckets is None:
            return [app for bucket in apps.values() if isinstance(bucket, list) for app in bucket]
        return [app for name in buckets for app in (apps.get(name) or [])]
