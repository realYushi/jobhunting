"""Fetch-free duplicate detection against the tracker and INBOX.

Builds O(1) lookup indexes from the tracker and current INBOX, then resolves a
human-readable duplicate/skip reason for a candidate. Runs before JD fetch and
package generation so we never spend on jobs already applied, skipped, or queued.
The helpers read ``source`` / ``job_id`` / ``company`` / ``title`` off either a
``JobListing`` (scrape stage) or a ``JobScore`` (package stage).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.app_state import ApplicationState
from lib.identity import (
    BoardKey,
    ManualKey,
    _norm_manual_field,
    try_manual_key,
)
from lib.inbox import parse_inbox
from lib.paths import tracker_path
from lib.tracker import BUCKETS, key_for_app_dict

if TYPE_CHECKING:
    from pathlib import Path

    from lib.identity import JobKey
    from lib.inbox import InboxItem
    from lib.scorer import JobScore


def _norm_identity_text(value: str | None) -> str:
    """Normalize company/title text for cross-id duplicate detection.

    Shares ManualKey's normalization so the (company, title) lookup index and
    ManualKey-keyed index can't disagree on what counts as the same job.
    """
    return _norm_manual_field(value or "")


def _build_company_title_index(tracker: dict) -> dict[tuple[str, str], list[dict]]:
    """Bucket all tracker applications by (company, title) for O(1) dedup lookup.

    The caller iterates many candidates; building this once is what avoids the
    full-tracker scan per candidate.
    """
    index: dict[tuple[str, str], list[dict]] = {}
    for bucket_items in tracker.get("applications", {}).values():
        for app in bucket_items:
            key = (
                _norm_identity_text(app.get("company")),
                _norm_identity_text(app.get("position")),
            )
            index.setdefault(key, []).append(app)
    return index


# Walk buckets in tracker.BUCKETS' declared order so the most-actionable status
# wins when a key appears in multiple buckets (active first). Any bucket not in
# BUCKETS still gets picked up via the sorted-keys fallback in
# _build_application_key_index, just at lower priority.
_BUCKET_PRIORITY: tuple[str, ...] = BUCKETS


def _build_application_key_index(tracker: dict) -> dict["JobKey", dict]:
    """Index tracker applications by their primary identity key.

    Buckets are walked in a fixed priority order (active first) so that when
    the same key appears in multiple buckets, the duplicate-reason message
    reflects the most actionable status rather than whichever bucket happened
    to be first in the JSON dict.
    """
    apps = tracker.get("applications", {}) or {}
    index: dict[JobKey, dict] = {}
    seen_buckets: set[str] = set()
    for bucket in (*_BUCKET_PRIORITY, *sorted(apps.keys())):
        if bucket in seen_buckets:
            continue
        seen_buckets.add(bucket)
        for app in apps.get(bucket, []) or []:
            try:
                index.setdefault(key_for_app_dict(app), app)
            except ValueError:
                continue
    return index


def _build_inbox_indexes(
    items: list["InboxItem"],
) -> tuple[dict["JobKey", "InboxItem"], dict[tuple[str, str], list["InboxItem"]]]:
    """Index current INBOX rows by key and by company/title.

    Rows whose company/title both normalise to empty are excluded from the
    (company, title) index so a malformed INBOX line can't seed a ('','')
    bucket that false-matches every other malformed score row downstream.
    """
    by_key: dict[JobKey, InboxItem] = {}
    by_company_title: dict[tuple[str, str], list[InboxItem]] = {}
    for item in items:
        try:
            by_key.setdefault(item.key, item)
        except ValueError:
            pass
        company = _norm_identity_text(item.company)
        title = _norm_identity_text(item.title)
        if not company or not title:
            continue
        by_company_title.setdefault((company, title), []).append(item)
    return by_key, by_company_title


def _score_board_key(item: "JobScore") -> BoardKey | None:
    # Strip before truthiness — BoardKey.__post_init__ checks non-empty BEFORE
    # stripping, so a whitespace-only id would slip past it and collapse to ''.
    source = (item.source or "").strip()
    job_id = str(item.job_id or "").strip()
    if not source or not job_id:
        return None
    return BoardKey(source=source, job_id=job_id)


_MANUAL_KEY_SENTINELS: frozenset[str] = frozenset({"", "unknown"})


def _score_manual_key(item: "JobScore") -> ManualKey | None:
    """Build a ManualKey for a score row, returning None for unusable inputs.

    Filters whitespace-only fields (which would crash ManualKey's strict
    constructor) and the "Unknown" placeholder that ``run_from_scores`` uses
    for missing company/title — without this guard, every malformed scored row
    would collide into a single ManualKey("unknown", "unknown") and falsely
    dedupe against each other.
    """
    company = (item.company or "").strip()
    title = (item.title or "").strip()
    if company.casefold() in _MANUAL_KEY_SENTINELS:
        return None
    if title.casefold() in _MANUAL_KEY_SENTINELS:
        return None
    return try_manual_key(company, title)


def _existing_company_title_matches(
    index: dict[tuple[str, str], list[dict]], item: "JobScore"
) -> list[dict]:
    """Return existing applications with the same company and title.

    Catches job boards re-listing the same role under a new id, where the
    exact (source, job_id) dedupe cannot help. Returns empty when the score
    row's company/title would resolve to a sentinel ("Unknown"/empty) — those
    placeholders must not be allowed to collide across distinct listings.
    """
    if _score_manual_key(item) is None:
        return []
    key = (_norm_identity_text(item.company), _norm_identity_text(item.title))
    return list(index.get(key, []))


def _duplicate_reason(
    item: "JobScore",
    *,
    application_key_index: dict["JobKey", dict],
    company_title_index: dict[tuple[str, str], list[dict]],
    inbox_key_index: dict["JobKey", "InboxItem"],
    inbox_company_title_index: dict[tuple[str, str], list["InboxItem"]],
    skipped_set: set["JobKey"],
) -> str | None:
    """Return a human-readable duplicate/skip reason, or None if new.

    This deliberately runs before JD fetching and package generation so we do
    not spend time rendering CVs/cover letters for jobs already applied,
    skipped, or sitting in INBOX.
    """
    board_key = _score_board_key(item)
    manual_key = _score_manual_key(item)

    if board_key and board_key in skipped_set:
        return f"previously skipped ({board_key.source} job_id={board_key.job_id})"
    if manual_key and manual_key in skipped_set:
        return "previously skipped by company/title"

    if board_key and board_key in application_key_index:
        app = application_key_index[board_key]
        return (
            f"existing tracker row ({app.get('status', 'Unknown')} "
            f"job_id={app.get('job_id', 'manual')})"
        )
    if manual_key and manual_key in application_key_index:
        app = application_key_index[manual_key]
        return f"existing tracker row ({app.get('status', 'Unknown')} manual)"

    matches = _existing_company_title_matches(company_title_index, item)
    if matches:
        match = matches[0]
        return (
            f"existing tracker company/title ({match.get('status', 'Unknown')} "
            f"job_id={match.get('job_id', 'manual')})"
        )

    if board_key and board_key in inbox_key_index:
        inbox_item = inbox_key_index[board_key]
        return f"already in INBOX {inbox_item.status} ({inbox_item.slug})"
    if manual_key and manual_key in inbox_key_index:
        inbox_item = inbox_key_index[manual_key]
        return f"already in INBOX {inbox_item.status} ({inbox_item.slug})"

    if manual_key is not None:
        inbox_key = (_norm_identity_text(item.company), _norm_identity_text(item.title))
        inbox_matches = inbox_company_title_index.get(inbox_key, [])
        if inbox_matches:
            inbox_item = inbox_matches[0]
            return f"already in INBOX {inbox_item.status} ({inbox_item.slug})"

    return None


class DedupGate:
    """One-call duplicate gate over the tracker and current INBOX.

    Builds all lookup indexes once at construction; call ``reason(item)`` per
    candidate. Indexes are a snapshot — construct a fresh gate after anything
    mutates the tracker or INBOX (e.g. reconcile); there is no staleness
    tracking.
    """

    def __init__(self, state: ApplicationState, inbox_path: Path) -> None:
        tracker = state.tracker
        inbox_key_index, inbox_company_title_index = _build_inbox_indexes(
            parse_inbox(inbox_path)
        )
        self._application_key_index = _build_application_key_index(tracker)
        self._company_title_index = _build_company_title_index(tracker)
        self._inbox_key_index = inbox_key_index
        self._inbox_company_title_index = inbox_company_title_index
        self._skipped_set = state.keyset("skipped")

    @classmethod
    def from_disk(cls, root: Path, inbox_path: Path) -> DedupGate:
        """Build a gate from the on-disk tracker + INBOX, fresh."""
        return cls(ApplicationState.load(tracker_path(root)), inbox_path)

    def reason(self, item: JobScore) -> str | None:
        """Return a human-readable duplicate/skip reason, or None if new."""
        return _duplicate_reason(
            item,
            application_key_index=self._application_key_index,
            company_title_index=self._company_title_index,
            inbox_key_index=self._inbox_key_index,
            inbox_company_title_index=self._inbox_company_title_index,
            skipped_set=self._skipped_set,
        )
