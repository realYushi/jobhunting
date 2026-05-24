"""LinkedIn application-status syncing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import shutil
import re
from typing import Any

from .harness_utils import load_script, parse_harness_json_output, run_harness
from .paths import active_dir, archive_dir, company_dirname, project_root, tracker_path
from .tracker import BUCKETS, load_tracker, save_tracker


@dataclass(frozen=True)
class StatusUpdate:
    """A tracker status change inferred from LinkedIn text."""

    company: str
    position: str
    from_bucket: str
    to_bucket: str
    status: str
    evidence: str


_STATUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "Rejected",
        r"\b(?:not selected by employer|application was not selected|no longer considering your application|we(?:'re| are) not moving forward|not moving forward|position has been filled|application (?:was )?unsuccessful|not selected)\b",
    ),
    (
        "Withdrawn",
        r"\b(?:application withdrawn|you withdrew your application|withdrawn your application)\b",
    ),
)

_SOURCE_BUCKETS: tuple[str, ...] = ("active", "interviews", "offers")
_LINKEDIN_SOURCE = "linkedin"


def _normalize_text(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _contains_phrase(haystack_lc: str, needle_lc: str) -> bool:
    """Substring match anchored to alphanumeric boundaries.

    Plain ``in`` lets a short company like "Ai" match inside "training"; the
    boundary guards require the needle to stand as its own token (punctuation
    and whitespace around it are fine).
    """
    if not needle_lc:
        return False
    pattern = re.escape(needle_lc)
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", haystack_lc) is not None


def fetch_linkedin_status_text(timeout: int = 180) -> dict[str, str]:
    """Fetch LinkedIn notifications + messaging text via browser-harness."""
    stdout, stderr, retcode = run_harness(load_script("linkedin-status"), timeout=timeout)
    if retcode != 0:
        raise RuntimeError(stderr or "linkedin-status harness failed")
    payloads = parse_harness_json_output(stdout)
    if not payloads:
        raise RuntimeError("linkedin-status harness returned no JSON payload")
    payload = payloads[-1]
    if not isinstance(payload, dict):
        raise RuntimeError("linkedin-status harness returned malformed payload")
    return {
        "notifications": str(payload.get("notifications") or ""),
        "messaging": str(payload.get("messaging") or ""),
    }


def _match_status(window_text: str) -> tuple[str, str] | None:
    for status, pattern in _STATUS_PATTERNS:
        if re.search(pattern, window_text, flags=re.IGNORECASE):
            return status, status.casefold()
    return None


def detect_status_updates(
    tracker: dict[str, Any],
    payload: dict[str, str],
) -> list[StatusUpdate]:
    """Detect LinkedIn-driven status changes for current tracker rows.

    Conservative on purpose: only LinkedIn-sourced applications in active /
    interviews / offers are eligible, and the evidence window must contain the
    company name plus a rejection/withdrawal phrase. When a company has more
    than one open application, the window must also name the position so one
    notice can't flip every role at that company.
    """
    text_sections = [str(payload.get(name) or "") for name in ("notifications", "messaging")]
    windows: list[str] = []
    for text in text_sections:
        lines = _normalize_text(text)
        for idx in range(len(lines)):
            window = " ".join(lines[max(0, idx - 3) : min(len(lines), idx + 4)])
            if window:
                windows.append(window)

    updates: list[StatusUpdate] = []
    seen: set[tuple[str, str, str]] = set()
    applications = tracker.get("applications", {}) or {}

    company_counts: dict[str, int] = {}
    for bucket in _SOURCE_BUCKETS:
        for app in applications.get(bucket, []) or []:
            if str(app.get("source") or "").strip().lower() != _LINKEDIN_SOURCE:
                continue
            company_lc = str(app.get("company") or "").strip().casefold()
            if company_lc:
                company_counts[company_lc] = company_counts.get(company_lc, 0) + 1

    for bucket in _SOURCE_BUCKETS:
        for app in applications.get(bucket, []) or []:
            if str(app.get("source") or "").strip().lower() != _LINKEDIN_SOURCE:
                continue

            company = str(app.get("company") or "").strip()
            position = str(app.get("position") or "").strip()
            if not company:
                continue

            company_lc = company.casefold()
            position_lc = position.casefold()
            # With multiple open roles at one company, a company-only match
            # would flip them all and a nearby unrelated notice could hit the
            # wrong row, so require the position in the window to disambiguate.
            require_position = company_counts.get(company_lc, 0) > 1
            for window in windows:
                window_lc = window.casefold()
                if not _contains_phrase(window_lc, company_lc):
                    continue
                if require_position and not _contains_phrase(window_lc, position_lc):
                    continue
                matched = _match_status(window)
                if not matched:
                    continue
                status, _ = matched
                key = (company_lc, position_lc, status.casefold())
                if key in seen:
                    break
                seen.add(key)
                updates.append(
                    StatusUpdate(
                        company=company,
                        position=position,
                        from_bucket=bucket,
                        to_bucket=status.casefold(),
                        status=status,
                        evidence=window[:400],
                    )
                )
                break

    return updates


def _move_active_dir(
    root: Path,
    company: str,
    job_id: str | None,
    from_bucket: str,
    to_bucket: str,
) -> tuple[str, str] | None:
    """Move the application dir into the archive bucket.

    Returns ``(src_rel, dest_rel)`` — both relative to ``root`` — so the caller
    can rewrite stored paths against the actual source dir instead of guessing
    its depth. Returns ``None`` when no matching dir exists.

    Looks first under ``active/``, but also checks ``archive/<from_bucket>/`` so
    a row whose dir was already filed under a non-``active`` bucket (e.g. an
    interview-stage app that was archived early) is still moved to the new
    bucket instead of leaving the tracker bucket and disk bucket divergent.
    """
    slug = company_dirname(company, job_id)
    fallback_slug = company_dirname(company, None)
    candidates: list[Path] = [
        active_dir(root) / slug,
        active_dir(root) / fallback_slug,
    ]
    if from_bucket and from_bucket != "active":
        candidates.append(archive_dir(root) / from_bucket / slug)
        candidates.append(archive_dir(root) / from_bucket / fallback_slug)
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        return None

    src_rel = str(src.relative_to(root))
    dest_parent = archive_dir(root) / to_bucket
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    if dest.exists():
        i = 2
        while (dest_parent / f"{src.name}-{i}").exists():
            i += 1
        dest = dest_parent / f"{src.name}-{i}"
    shutil.move(str(src), str(dest))
    return src_rel, str(dest.relative_to(root))


def apply_status_updates(
    tracker: dict[str, Any],
    updates: list[StatusUpdate],
    *,
    root: Path | None = None,
    today: date | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Apply detected status updates to the tracker and archive folders."""
    root = root or project_root()
    stamp = (today or date.today()).isoformat()
    applications = tracker.setdefault("applications", {})
    for bucket in BUCKETS:
        applications.setdefault(bucket, [])

    applied: list[dict[str, Any]] = []

    for update in updates:
        bucket_items = applications.get(update.from_bucket, []) or []
        match_idx = None
        for idx, app in enumerate(bucket_items):
            if str(app.get("company") or "").strip() != update.company:
                continue
            if str(app.get("position") or "").strip() != update.position:
                continue
            match_idx = idx
            break
        if match_idx is None:
            continue

        app = dict(bucket_items.pop(match_idx))
        app["status"] = update.status
        app[f"{update.to_bucket}_at"] = stamp
        app["status_evidence"] = update.evidence

        moved = None
        if not dry_run:
            moved = _move_active_dir(
                root,
                str(app.get("company") or ""),
                app.get("job_id"),
                update.from_bucket,
                update.to_bucket,
            )
        if moved and app.get("pdf_path"):
            src_rel, moved_dir = moved
            old_pdf = Path(str(app["pdf_path"]))
            # Normalize to a path comparable against `src_rel` (a root-relative
            # string). Absolute paths stored under root must be re-rooted first
            # — otherwise the relative_to below raises and the except branch
            # silently drops the `documents/` segment.
            if old_pdf.is_absolute():
                try:
                    old_pdf = old_pdf.relative_to(root)
                except ValueError:
                    old_pdf = Path(old_pdf.name)
            try:
                sub = old_pdf.relative_to(src_rel)
            except ValueError:
                # pdf wasn't stored under the moved dir; keep just the filename.
                sub = Path(old_pdf.name)
            app["pdf_path"] = str(Path(moved_dir) / sub)

        applications[update.to_bucket].append(app)
        applied.append(
            {
                "company": app.get("company"),
                "position": app.get("position"),
                "from_bucket": update.from_bucket,
                "to_bucket": update.to_bucket,
                "status": update.status,
            }
        )

    return applied


def sync_linkedin_statuses(
    root: Path | None = None,
    *,
    dry_run: bool = False,
    timeout: int = 180,
) -> list[dict[str, Any]]:
    """Fetch LinkedIn status text and apply matching tracker updates."""
    root = root or project_root()
    tracker_file = tracker_path(root)
    tracker = load_tracker(tracker_file)
    payload = fetch_linkedin_status_text(timeout=timeout)
    updates = detect_status_updates(tracker, payload)
    applied = apply_status_updates(tracker, updates, root=root, dry_run=dry_run)
    if applied and not dry_run:
        save_tracker(tracker_file, tracker)
    return applied
