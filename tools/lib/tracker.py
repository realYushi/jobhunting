"""Application tracker read/write helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .identity import BoardKey, JobKey, ManualKey, from_dict, key_from_args

# Bumped when the on-disk schema changes. v8 = `seen` ledger replaced by
# `last_scrape` per-source date watermark in the sidecar; v7 = `seen` moved
# to a sidecar ledger; v6 = flat seen/skipped lists of typed JobKey dicts
# (was bucketed seen_jobs/skipped_jobs in v5.x).
TRACKER_VERSION = "8.0"
BUCKETS = ("active", "interviews", "offers", "rejected", "withdrawn")
LEDGER_NAME = "application-ledger.json"


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
    # `d.get("company") or ""` — bare default of "" would not fire when the
    # stored value is explicitly None, and `str(None) == "None"` would then
    # produce a bogus truthy ManualKey("none","none") for every null-company row.
    return key_from_args(
        d.get("source"),
        d.get("job_id"),
        str(d.get("company") or ""),
        str(d.get("position") or ""),
    )


def empty_tracker(today: date | None = None) -> dict[str, Any]:
    """Return a valid empty tracker structure."""
    stamp = (today or date.today()).isoformat()
    return {
        "meta": {"last_updated": stamp, "version": TRACKER_VERSION},
        "applications": {bucket: [] for bucket in BUCKETS},
        "skipped": [],
    }


def _migrate_legacy_skipped(tracker: dict[str, Any]) -> None:
    """Convert v5.x bucketed skipped_jobs into v6 flat key list.

    Old shape:
      skipped_jobs = {source: [job_id, ...], "manual": ["company|position", ...]}

    New shape:
      skipped = [BoardKey.to_dict() | ManualKey.to_dict(), ...]

    Idempotent: a tracker already on the new shape passes through unchanged.

    Note: `seen_jobs` / `seen` from pre-v8 files are stripped here; the
    seen ledger was replaced by the `last_scrape` watermark in v8.
    """
    # Strip legacy seen data (pre-v8). Defensive: old on-disk files may still
    # carry inline `seen` or `seen_jobs`; discard them silently on load.
    tracker.pop("seen_jobs", None)
    tracker.pop("seen", None)

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


def _ledger_for(tracker_file: Path) -> Path:
    """Sidecar ledger path sitting next to the tracker file."""
    return tracker_file.with_name(LEDGER_NAME)


def _load_watermark(ledger_file: Path) -> dict[str, str]:
    """Return the ``last_scrape`` dict from the sidecar, or ``{}`` when absent.

    Returns ``{}`` on any missing/malformed sidecar so callers fall back to
    the initial-lookback window for every source.
    """
    if not ledger_file.exists():
        return {}
    with open(ledger_file) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    watermark = data.get("last_scrape")
    return watermark if isinstance(watermark, dict) else {}


def _sorted_key_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable, deterministic ordering for key-dict lists so the serialized
    output doesn't reshuffle each run (sets have no order) and churn the diff."""
    return sorted(items or [], key=lambda d: json.dumps(d, sort_keys=True))


def load_tracker(path: Path) -> dict[str, Any]:
    """Load tracker JSON, creating an in-memory default when missing.

    Migrates v5.x bucketed skipped_jobs to flat key lists on read.
    Pre-v8 inline `seen`/`seen_jobs` are stripped; the seen ledger was
    replaced by the `last_scrape` watermark in v8.
    """
    if not path.exists():
        return empty_tracker()
    with open(path) as f:
        tracker = json.load(f)
    tracker.setdefault("meta", {})
    apps = tracker.setdefault("applications", {})
    for bucket in BUCKETS:
        apps.setdefault(bucket, [])

    _migrate_legacy_skipped(tracker)
    tracker["meta"]["version"] = TRACKER_VERSION
    return tracker


def load_last_scrape(tracker_path: Path) -> dict[str, str]:
    """Return the per-source ``last_scrape`` watermark from the sidecar ledger.

    Returns ``{}`` when no sidecar exists yet (first run → use initial lookback).
    """
    return _load_watermark(_ledger_for(tracker_path))


def save_last_scrape(tracker_path: Path, watermark: dict[str, str]) -> None:
    """Persist the per-source ``last_scrape`` watermark to the sidecar ledger.

    Writes ``{"last_scrape": {source: "YYYY-MM-DD", ...}}`` (keys sorted so the
    diff is deterministic). Skips the write when the serialised content is
    byte-for-byte identical to what is already on disk (no-op guard).
    """
    ledger_file = _ledger_for(tracker_path)
    ledger_doc = {"last_scrape": dict(sorted(watermark.items()))}
    ledger_text = json.dumps(ledger_doc, indent=2) + "\n"
    if ledger_file.exists() and ledger_file.read_text() == ledger_text:
        return
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_file, "w") as f:
        f.write(ledger_text)


def save_tracker(
    path: Path, tracker: dict[str, Any], today: date | None = None
) -> None:
    """Persist the tracker to disk.

    tracker.json holds meta + applications + skipped (+ skip_details).
    The `last_scrape` watermark is written separately via `save_last_scrape`.
    Skips the write when the serialised output is byte-for-byte identical to
    disk (no-op guard) so mtimes and downstream watchers don't churn.
    """
    # Strip any legacy keys that snuck in.
    tracker.pop("seen_jobs", None)
    tracker.pop("skipped_jobs", None)
    tracker.pop("seen", None)
    meta = tracker.setdefault("meta", {})
    meta["version"] = TRACKER_VERSION

    # Key lists are sorted so set-derived ordering doesn't reshuffle the diff.
    main_doc = dict(tracker)
    if "skipped" in main_doc:
        main_doc["skipped"] = _sorted_key_dicts(main_doc["skipped"])

    main_text = json.dumps(main_doc, indent=2) + "\n"
    if path.exists() and path.read_text() == main_text:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    meta["last_updated"] = (today or date.today()).isoformat()
    main_text = json.dumps(main_doc, indent=2) + "\n"
    with open(path, "w") as f:
        f.write(main_text)


def upsert_active_application(
    tracker: dict[str, Any],
    record: ApplicationRecord,
) -> dict[str, Any]:
    """Insert or replace one active application.

    Dedup key is (source, job_id) when the record carries both, else falls back
    to (company.lower(), position.lower()).
    """
    active = tracker.setdefault("applications", {}).setdefault("active", [])
    key = record.key
    payload = record.to_json()
    for idx, existing in enumerate(active):
        # key_for_app_dict now raises on rows with neither (source,id) nor
        # (company,position); skip those so one legacy/malformed row can't
        # crash every future upsert.
        try:
            existing_key = key_for_app_dict(existing)
        except ValueError:
            continue
        if existing_key == key:
            active[idx] = {**existing, **payload}
            break
    else:
        active.append(payload)

    return tracker


def load_keyset(tracker: dict[str, Any], field: str) -> set[JobKey]:
    """Materialise the flat key list at tracker[field] as a set[JobKey].

    Skips entries that fail to parse (e.g. legacy ManualKey dicts with empty
    fields written by the pre-strict constructor) rather than raising — one
    bad row should not poison the whole keyset and crash callers.
    """
    out: set[JobKey] = set()
    for d in tracker.get(field, []):
        try:
            out.add(from_dict(d))
        except (ValueError, KeyError, TypeError, AttributeError):
            # AttributeError covers null/non-dict entries (from_dict calls
            # d.get(...) on a non-dict); the others cover malformed dicts.
            continue
    return out


def store_keyset(tracker: dict[str, Any], field: str, keys: set[JobKey]) -> None:
    """Persist a set[JobKey] back to tracker[field] as a list of dicts."""
    tracker[field] = [k.to_dict() for k in keys]


def mark_skipped_key(tracker: dict[str, Any], key: JobKey) -> None:
    """Record that this job was skipped, so scrapers never re-suggest it."""
    keys = load_keyset(tracker, "skipped")
    keys.add(key)
    store_keyset(tracker, "skipped", keys)


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
    skipped = load_keyset(tracker, "skipped")
    if primary in skipped:
        return True
    return fallback is not None and fallback in skipped


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
