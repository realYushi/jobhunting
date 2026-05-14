"""Application tracker read/write helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

TRACKER_VERSION = "5.1"
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


def _identity_key(record: Any) -> tuple[str, ...]:
    """Return a comparable key for dedup.

    Prefer (source, job_id) when the scraper supplied both; otherwise fall back
    to the historical (company, position) key so manually pasted JDs still
    upsert correctly.
    """
    if isinstance(record, ApplicationRecord):
        job_id = record.job_id
        source = record.source
        company = record.company
        position = record.position
    else:
        job_id = record.get("job_id")
        source = record.get("source")
        company = str(record.get("company", ""))
        position = str(record.get("position", ""))

    if job_id and source:
        return ("by-id", str(source).lower(), str(job_id))
    return ("by-name", company.lower(), position.lower())


def empty_tracker(today: date | None = None) -> dict[str, Any]:
    """Return a valid empty tracker structure."""
    stamp = (today or date.today()).isoformat()
    return {
        "meta": {"last_updated": stamp, "version": TRACKER_VERSION},
        "applications": {bucket: [] for bucket in BUCKETS},
        "seen_jobs": {},
    }


def load_tracker(path: Path) -> dict[str, Any]:
    """Load tracker JSON, creating an in-memory default when missing."""
    if not path.exists():
        return empty_tracker()
    with open(path) as f:
        tracker = json.load(f)
    tracker.setdefault("meta", {})
    tracker["meta"].setdefault("version", TRACKER_VERSION)
    apps = tracker.setdefault("applications", {})
    for bucket in BUCKETS:
        apps.setdefault(bucket, [])
    tracker.setdefault("seen_jobs", {})
    return tracker


def save_tracker(
    path: Path, tracker: dict[str, Any], today: date | None = None
) -> None:
    """Persist tracker JSON with a refreshed last_updated date."""
    tracker.setdefault("meta", {})["last_updated"] = (today or date.today()).isoformat()
    tracker["meta"].setdefault("version", TRACKER_VERSION)
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
    key = _identity_key(record)
    payload = record.to_json()
    for idx, existing in enumerate(active):
        if _identity_key(existing) == key:
            active[idx] = {**existing, **payload}
            break
    else:
        active.append(payload)

    if record.job_id and record.source:
        mark_seen(tracker, record.source, record.job_id)
    return tracker


def mark_seen(tracker: dict[str, Any], source: str, job_id: str) -> None:
    """Record that this source/job_id was surfaced, so scrapers can dedupe."""
    seen = tracker.setdefault("seen_jobs", {}).setdefault(source.lower(), [])
    if job_id not in seen:
        seen.append(job_id)


def is_seen(tracker: dict[str, Any], source: str, job_id: str) -> bool:
    """Has this source/job_id already been surfaced in a previous run?"""
    return job_id in tracker.get("seen_jobs", {}).get(source.lower(), [])


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
