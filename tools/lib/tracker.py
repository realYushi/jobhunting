"""Application tracker read/write helpers."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .identity import BoardKey, JobKey, ManualKey, from_dict, key_from_args

# Bumped when the on-disk schema changes. v6 = flat seen/skipped lists of
# typed JobKey dicts (was bucketed seen_jobs/skipped_jobs in v5.x).
TRACKER_VERSION = "6.0"
BUCKETS = ("active", "interviews", "offers", "rejected", "withdrawn")


@dataclass(frozen=True)
class ApplicationRecord:
    """Normalized application tracker record."""

    company: str
    position: str
    date_applied: str
    status: str = "In Progress"
    priority: str = "Medium"
    resume_id: str | None = None
    pdf_path: str | None = None
    job_id: str | None = None
    source: str | None = None
    url: str | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "company": self.company,
            "position": self.position,
            "date_applied": self.date_applied,
            "status": self.status,
            "priority": self.priority,
        }
        for field in ("resume_id", "pdf_path", "job_id", "source", "url"):
            value = getattr(self, field)
            if value:
                data[field] = value
        return data

    @property
    def key(self) -> JobKey:
        """BoardKey when scraper supplied source+id, else ManualKey."""
        return key_from_args(self.source, self.job_id, self.company, self.position)


def key_for_app_dict(d: dict[str, Any]) -> JobKey:
    """Same identity rule as ApplicationRecord.key, but for the raw dict form
    stored under tracker['applications'][bucket]. Used so dict-vs-record
    dedup comparisons land on the exact same key."""
    return key_from_args(
        d.get("source"),
        d.get("job_id"),
        str(d.get("company", "")),
        str(d.get("position", "")),
    )


def empty_tracker(today: date | None = None) -> dict[str, Any]:
    """Return a valid empty tracker structure."""
    stamp = (today or date.today()).isoformat()
    return {
        "meta": {"last_updated": stamp, "version": TRACKER_VERSION},
        "applications": {bucket: [] for bucket in BUCKETS},
        "seen": [],
        "skipped": [],
    }


def _migrate_legacy_seen_skipped(tracker: dict[str, Any]) -> None:
    """Convert v5.x bucketed seen_jobs/skipped_jobs into v6 flat key lists.

    Old shape:
      seen_jobs    = {source: [job_id, ...]}
      skipped_jobs = {source: [job_id, ...], "manual": ["company|position", ...]}

    New shape:
      seen    = [BoardKey.to_dict() | ManualKey.to_dict(), ...]
      skipped = [BoardKey.to_dict() | ManualKey.to_dict(), ...]

    Idempotent: a tracker already on the new shape passes through unchanged.
    """
    if "seen_jobs" in tracker:
        seen_legacy = tracker.pop("seen_jobs") or {}
        seen_keys: list[JobKey] = []
        # Seen only ever held source-bucketed ids; no manual bucket existed.
        for source, ids in seen_legacy.items():
            for job_id in ids:
                if job_id:
                    seen_keys.append(BoardKey(source=source, job_id=str(job_id)))
        # Merge with any pre-existing v6 list so re-migration is harmless.
        existing = tracker.get("seen", []) or []
        tracker["seen"] = _dedup_key_dicts(
            [k.to_dict() for k in seen_keys] + list(existing)
        )

    if "skipped_jobs" in tracker:
        skip_legacy = tracker.pop("skipped_jobs") or {}
        skip_keys: list[JobKey] = []
        for source, entries in skip_legacy.items():
            if source == "manual":
                for entry in entries:
                    if "|" not in entry:
                        continue
                    company, position = entry.split("|", 1)
                    if company and position:
                        skip_keys.append(ManualKey(company_lc=company, position_lc=position))
            else:
                for job_id in entries:
                    if job_id:
                        skip_keys.append(BoardKey(source=source, job_id=str(job_id)))
        existing = tracker.get("skipped", []) or []
        tracker["skipped"] = _dedup_key_dicts(
            [k.to_dict() for k in skip_keys] + list(existing)
        )

    tracker.setdefault("seen", [])
    tracker.setdefault("skipped", [])


def _dedup_key_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate key dicts, preserving first-seen order."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        sig = tuple(sorted(item.items()))
        if sig not in seen:
            seen.add(sig)
            out.append(item)
    return out


def load_tracker(path: Path) -> dict[str, Any]:
    """Load tracker JSON, creating an in-memory default when missing.

    Migrates v5.x bucketed seen_jobs/skipped_jobs to v6 flat key lists on read.
    """
    if not path.exists():
        return empty_tracker()
    with open(path) as f:
        tracker = json.load(f)
    tracker.setdefault("meta", {})
    apps = tracker.setdefault("applications", {})
    for bucket in BUCKETS:
        apps.setdefault(bucket, [])
    _migrate_legacy_seen_skipped(tracker)
    tracker["meta"]["version"] = TRACKER_VERSION
    return tracker


def save_tracker(
    path: Path, tracker: dict[str, Any], today: date | None = None
) -> None:
    """Persist tracker JSON with a refreshed last_updated date.

    Skips the write (and the last_updated bump) when serialized output matches
    the existing file byte-for-byte, so no-op flows don't churn the mtime or
    re-trigger downstream watchers.
    """
    # Strip any legacy keys that snuck in (defensive: writers shouldn't add them
    # post-migration, but a hand-edit upstream shouldn't poison the next read).
    tracker.pop("seen_jobs", None)
    tracker.pop("skipped_jobs", None)
    tracker.setdefault("meta", {})["version"] = TRACKER_VERSION

    # Compare the current dict against the on-disk file before bumping
    # last_updated. If they match, the caller's mutation was a no-op and we
    # leave both the contents and the mtime alone.
    candidate_text = json.dumps(tracker, indent=2) + "\n"
    if path.exists() and path.read_text() == candidate_text:
        return

    tracker["meta"]["last_updated"] = (today or date.today()).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(tracker, f, indent=2)
        f.write("\n")


def upsert_active_application(
    tracker: dict[str, Any],
    record: ApplicationRecord,
) -> dict[str, Any]:
    """Insert or replace one active application.

    Dedup key is (source, job_id) when the record carries both, else falls back
    to (company.lower(), position.lower()). If the record has a job_id/source,
    we also mark it seen so future scrape passes skip it.
    """
    active = tracker.setdefault("applications", {}).setdefault("active", [])
    key = record.key
    payload = record.to_json()
    for idx, existing in enumerate(active):
        if key_for_app_dict(existing) == key:
            active[idx] = {**existing, **payload}
            break
    else:
        active.append(payload)

    if record.job_id and record.source:
        mark_seen_key(tracker, BoardKey(source=record.source, job_id=record.job_id))
    return tracker


def _load_keyset(tracker: dict[str, Any], field: str) -> set[JobKey]:
    """Materialise the flat key list at tracker[field] as a set[JobKey]."""
    return {from_dict(d) for d in tracker.get(field, [])}


def _store_keyset(tracker: dict[str, Any], field: str, keys: set[JobKey]) -> None:
    """Persist a set[JobKey] back to tracker[field] as a list of dicts."""
    tracker[field] = [k.to_dict() for k in keys]


def mark_seen_key(tracker: dict[str, Any], key: JobKey) -> None:
    """Record that this listing was surfaced, so scrapers can dedupe."""
    keys = _load_keyset(tracker, "seen")
    keys.add(key)
    _store_keyset(tracker, "seen", keys)


def is_seen_key(tracker: dict[str, Any], key: JobKey) -> bool:
    """Has this listing already been surfaced in a previous run?"""
    return key in _load_keyset(tracker, "seen")


def mark_skipped_key(tracker: dict[str, Any], key: JobKey) -> None:
    """Record that this job was skipped, so scrapers never re-suggest it."""
    keys = _load_keyset(tracker, "skipped")
    keys.add(key)
    _store_keyset(tracker, "skipped", keys)


def is_skipped_key(
    tracker: dict[str, Any],
    primary: JobKey,
    fallback: JobKey | None = None,
) -> bool:
    """Was this job skipped, checking primary then optional fallback key?

    Scrapers pass a BoardKey as primary plus a ManualKey fallback so the same
    posting re-listed under a different id is still caught when the original
    was skipped manually (no board id at the time).
    """
    skipped = _load_keyset(tracker, "skipped")
    if primary in skipped:
        return True
    return fallback is not None and fallback in skipped


def seen_by_source(tracker: dict[str, Any]) -> dict[str, set[str]]:
    """Return seen BoardKeys re-bucketed as ``{source: {job_id, ...}}``.

    Helper for callers that paginate per source and want O(1) "have I seen
    this id from this source?" checks. ManualKeys aren't represented.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for key in _load_keyset(tracker, "seen"):
        if isinstance(key, BoardKey):
            out[key.source].add(key.job_id)
    return dict(out)


def tracker_summary(tracker: dict[str, Any]) -> list[str]:
    """Return human-readable tracker status lines."""
    apps = tracker.get("applications", {})
    lines = []
    for bucket in BUCKETS:
        items = apps.get(bucket, [])
        lines.append(f"{bucket}: {len(items)}")
        for item in items:
            company = item.get("company", "Unknown")
            position = item.get("position", "Unknown role")
            marker = ""
            if not item.get("pdf_path") and bucket == "active":
                marker = " (missing PDF)"
            lines.append(f"  - {company} — {position}{marker}")
    return lines
