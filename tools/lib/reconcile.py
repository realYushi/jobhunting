"""INBOX.md reconciliation utilities."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .identity import BoardKey, JobKey, ManualKey, key_from_args
from .paths import (
    active_dir,
    archive_dir,
    company_dirname,
    inbox_path as default_inbox_path,
    tracker_path as tracker_file,
)
from .tracker import (
    key_for_app_dict,
    load_keyset,
    load_tracker,
    save_tracker,
    store_keyset,
)


@dataclass(frozen=True)
class InboxItem:
    """A parsed row from INBOX.md."""

    slug: str
    status: str  # "[ ]", "[x]", or "[~]"
    title: str
    company: str
    score: int | None = None
    job_path: Path | None = None
    cv_path: Path | None = None
    cover_path: Path | None = None
    apply_url: str | None = None
    source: str | None = None
    job_id: str | None = None

    @property
    def key(self) -> JobKey:
        """BoardKey when Apply URL yielded source+id, else ManualKey."""
        return key_from_args(self.source, self.job_id, self.company, self.title)


# Map from URL host substring to (source label, job-id regex).
# Tracker rows are written with these same source labels by the scrapers,
# so extracting them here lets BoardKey match the tracker row during reconcile.
_URL_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("seek.com", "seek", r"/job/(\d+)"),
    ("linkedin.com", "linkedin", r"/jobs/view/(\d+)"),
    ("hiring.cafe", "hiringcafe", r"/(?:viewjob|job)/([A-Za-z0-9]+)"),
    ("workingnomads.com", "workingnomads", r"/jobs/([^/?#]+)"),
    ("wellfound.com", "wellfound", r"/jobs/(\d+)"),
    ("weworkremotely.com", "weworkremotely", r"/remote-jobs/([^/?#]+)"),
)


def _parse_apply_url(url: str | None) -> tuple[str | None, str | None]:
    """Return (source, job_id) from a known job-board URL, or (None, None)."""
    if not url:
        return None, None
    for host, source, id_pattern in _URL_SOURCES:
        if host in url:
            m = re.search(id_pattern, url)
            return source, (m.group(1) if m else None)
    return None, None


@dataclass(frozen=True)
class ReconcileResult:
    """Summary of reconciliation actions."""

    submitted: list[str]
    skipped: list[str]
    kept: list[str]
    errors: list[str]
    cleaned_active: list[str] = field(default_factory=list)


_INBOX_PATTERN = re.compile(
    r"""^-\s+\[(?P<status>[ x~])\]\s*\*\*(?P<title>[^*]+)\s*\*\*\s*@\s*(?P<company>[^(]+)(?:\s*\(score:\s*(?P<score>\d+)\))?""",
    re.MULTILINE,
)


def parse_inbox(inbox_path: Path) -> list[InboxItem]:
    """Extract structured items from INBOX.md checkbox list."""
    if not inbox_path.exists():
        return []

    text = inbox_path.read_text()
    items: list[InboxItem] = []

    for line in text.splitlines():
        match = _INBOX_PATTERN.search(line)
        if not match:
            continue

        status_raw = match.group("status")
        status = {
            " ": "[ ]",
            "x": "[x]",
            "~": "[~]",
        }.get(status_raw, "[ ]")

        title = match.group("title").strip()
        company = match.group("company").strip()
        score_str = match.group("score")
        score = int(score_str) if score_str else None

        url_match = re.search(r"\[Apply\s*↗\]\((https?://[^)]+)\)", line)
        apply_url = url_match.group(1) if url_match else None
        source, job_id = _parse_apply_url(apply_url)

        # Slug = the on-disk active dir name. Derived from company + job_id so
        # the same company applied for twice (different listings) doesn't
        # collide. Matches company_dirname used by workflow.create_application_package.
        slug = company_dirname(company, job_id)

        job_match = re.search(r"\[JD\]\(\.*/([^)]+?)\)", line)
        job_path = (
            Path(
                f"applications/active/{slug}/{job_match.group(1) if job_match else 'job.md'}"
            )
            if job_match
            else None
        )

        cv_match = re.search(r"\[CV\]\(\.*/([^)]+?)\)", line)
        cv_path = (
            Path(
                f"applications/active/{slug}/{cv_match.group(1) if cv_match else 'cv.pdf'}"
            )
            if cv_match
            else None
        )

        cover_match = re.search(r"\[Letter\]\(\.*/([^)]+?)\)", line)
        cover_path = (
            Path(
                f"applications/active/{slug}/{cover_match.group(1) if cover_match else 'cover.md'}"
            )
            if cover_match
            else None
        )

        items.append(
            InboxItem(
                slug=slug,
                status=status,
                title=title,
                company=company,
                score=score,
                job_path=job_path,
                cv_path=cv_path,
                cover_path=cover_path,
                apply_url=apply_url,
                source=source,
                job_id=job_id,
            )
        )

    return items


def slug_from_company(company: str, existing: list[str]) -> str:
    """Generate a unique directory slug from company name."""
    base = company.lower().replace(" ", "-").replace(",", "").replace("'", "")
    base = re.sub(r"[^a-z0-9-]", "", base)
    base = re.sub(r"-+", "-", base).strip("-")

    if base not in existing:
        return base

    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if candidate not in existing:
            return candidate
    return base


def _unique_archive_dest(dest_dir: Path) -> Path:
    """Return a non-existing archive destination, preserving prior archives."""
    if not dest_dir.exists():
        return dest_dir

    for i in range(2, 1000):
        candidate = dest_dir.with_name(f"{dest_dir.name}-{i}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Could not find unique archive path for {dest_dir}")


def _move_active_dir_to_archive(
    src_dir: Path,
    root: Path,
    archive_type: str,
    dry_run: bool = False,
) -> Path | None:
    """Move an active application directory to an archive bucket."""
    if not src_dir.exists():
        return None

    dest_dir = archive_dir(root) / archive_type / src_dir.name
    dest_dir = _unique_archive_dest(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        shutil.move(str(src_dir), str(dest_dir))
    return dest_dir


def move_to_archive(item: InboxItem, root: Path, archive_type: str) -> None:
    """Move an application directory to the appropriate archive folder."""
    _move_active_dir_to_archive(active_dir(root) / item.slug, root, archive_type)


def _archive_type_for_tracker_row(bucket: str, status: str | None) -> str | None:
    """Return archive bucket for tracker rows that should not be in active/."""
    status_lc = (status or "").strip().casefold()
    if status_lc in {"submitted", "skipped", "rejected", "withdrawn"}:
        return status_lc
    if bucket in {"rejected", "withdrawn"}:
        return bucket
    return None


def _tracker_slug_indexes(tracker: dict) -> tuple[set[str], dict[str, str]]:
    """Build keep/archive slug indexes from tracker records."""
    keep_slugs: set[str] = set()
    archive_slugs: dict[str, str] = {}

    for bucket, apps in tracker.get("applications", {}).items():
        if not isinstance(apps, list):
            continue

        for app in apps:
            company = app.get("company", "")
            slugs = {
                company_dirname(company, app.get("job_id")),
                company_dirname(company, None),
            }
            archive_type = _archive_type_for_tracker_row(bucket, app.get("status"))
            if archive_type:
                for slug in slugs:
                    archive_slugs.setdefault(slug, archive_type)
            else:
                keep_slugs.update(slugs)

    return keep_slugs, archive_slugs


def cleanup_active_folder(
    root: Path,
    tracker: dict,
    inbox_items: list[InboxItem],
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """Archive active/ directories that are no longer active.

    A directory is kept when it is referenced by an active tracker row or by a
    current INBOX row. Directories linked to submitted/skipped/rejected/
    withdrawn tracker rows are moved to that matching archive bucket. Unknown
    leftovers are moved to archive/orphaned instead of being deleted.
    """
    base = active_dir(root)
    if not base.exists():
        return [], []

    tracker_keep_slugs, tracker_archive_slugs = _tracker_slug_indexes(tracker)
    inbox_keep_slugs = {item.slug for item in inbox_items}

    cleaned: list[str] = []
    errors: list[str] = []

    for src_dir in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name):
        slug = src_dir.name
        if slug in tracker_keep_slugs or slug in inbox_keep_slugs:
            continue

        archive_type = tracker_archive_slugs.get(slug, "orphaned")
        try:
            dest = _move_active_dir_to_archive(
                src_dir,
                root,
                archive_type,
                dry_run=dry_run,
            )
            if dest:
                cleaned.append(f"{slug} → archive/{archive_type}/{dest.name}")
        except Exception as exc:
            errors.append(f"{slug}: {exc}")

    return cleaned, errors


def remove_inbox_rows(inbox_path: Path, items: list[InboxItem]) -> None:
    """Remove archived rows from INBOX.md in one pass."""
    if not inbox_path.exists():
        return

    text = inbox_path.read_text()
    lines = text.splitlines()
    new_lines = []

    for line in lines:
        should_remove = False
        for item in items:
            if item.status in line and item.company in line and item.title in line:
                should_remove = True
                break
        if not should_remove:
            new_lines.append(line)

    inbox_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""))


def reconcile(
    root: Path,
    inbox_path: Path | None = None,
    dry_run: bool = False,
) -> ReconcileResult:
    """Parse INBOX.md and archive submitted/skipped items.

    - [x] → move to archive/submitted/, set submitted_at in tracker
    - [~] → move to archive/skipped/, add to never-suggest list
    - [ ] → leave alone

    Returns the list of actions taken.
    """
    if inbox_path is None:
        inbox_path = default_inbox_path(root)

    items = parse_inbox(inbox_path)
    tracker = load_tracker(tracker_file(root))
    skipped_set = load_keyset(tracker, "skipped")

    submitted: list[str] = []
    skipped: list[str] = []
    kept: list[str] = []
    errors: list[str] = []
    cleaned_active: list[str] = []

    for item in items:
        try:
            if item.status == "[x]":
                # Archive as submitted
                if not dry_run:
                    move_to_archive(item, root, "submitted")
                    active = tracker.get("applications", {}).get("active", [])
                    item_key = item.key
                    for idx, app in enumerate(active):
                        if key_for_app_dict(app) == item_key:
                            active[idx]["status"] = "Submitted"
                            active[idx]["submitted_at"] = date.today().isoformat()
                            break
                submitted.append(f"{item.company} — {item.title}")

            elif item.status == "[~]":
                # Archive as skipped
                if not dry_run:
                    move_to_archive(item, root, "skipped")
                    # Write both variants: ManualKey catches reposts under a
                    # different id; BoardKey gives fast id-based lookup when
                    # we already know the source/id at parse time.
                    if item.company and item.title:
                        skipped_set.add(
                            ManualKey(company_lc=item.company, position_lc=item.title)
                        )
                    if item.source and item.job_id:
                        skipped_set.add(
                            BoardKey(source=item.source, job_id=item.job_id)
                        )
                skipped.append(f"{item.company} — {item.title}")

            else:
                kept.append(f"{item.company} — {item.title}")

        except Exception as e:
            errors.append(f"{item.company}: {e}")

    if not dry_run and (submitted or skipped):
        store_keyset(tracker, "skipped", skipped_set)
        # Remove archived rows from INBOX in one pass
        archived = [item for item in items if item.status in ("[x]", "[~]")]
        remove_inbox_rows(inbox_path, archived)
        save_tracker(tracker_file(root), tracker)

    cleaned_active, cleanup_errors = cleanup_active_folder(
        root,
        tracker,
        items,
        dry_run=dry_run,
    )
    errors.extend(cleanup_errors)

    return ReconcileResult(
        submitted=submitted,
        skipped=skipped,
        kept=kept,
        errors=errors,
        cleaned_active=cleaned_active,
    )
