"""Path helpers for the job-hunting project."""

from __future__ import annotations

import re
from pathlib import Path


def project_root() -> Path:
    """Return the project root directory (parent of tools/)."""
    return Path(__file__).resolve().parents[2]


def slugify(value: str) -> str:
    """Create a filesystem/URL-safe slug from a human label."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "application"


def company_dirname(company: str, job_id: str | None = None) -> str:
    """Return the active-dir name used for a company.

    When job_id is supplied, the dir is namespaced as ``{Company}-{id8}`` so
    multiple listings from the same company don't collide on disk. Manual flows
    (no job_id) keep the bare company name for backward compatibility.
    """
    safe = re.sub(r"[^a-zA-Z0-9._ -]+", "", company).strip()
    base = safe or slugify(company)
    if job_id:
        suffix = re.sub(r"[^a-zA-Z0-9]", "", str(job_id))[:8]
        if suffix:
            return f"{base}-{suffix}"
    return base


def company_dir(root: Path, company: str, job_id: str | None = None) -> Path:
    """Return the active application directory for a company."""
    return root / "applications" / "active" / company_dirname(company, job_id)


def templates_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "templates"


def base_resume_path(root: Path | None = None) -> Path:
    return templates_dir(root) / "base-resume.json"


def tracker_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "applications" / "application-tracker.json"


def active_dir(root: Path | None = None) -> Path:
    """Return the active applications directory."""
    return (root or project_root()) / "applications" / "active"


def archive_dir(root: Path | None = None) -> Path:
    """Return the archive directory (parent of submitted/skipped)."""
    return (root or project_root()) / "applications" / "archive"


def inbox_path(root: Path | None = None) -> Path:
    """Return the INBOX.md path."""
    return (root or project_root()) / "applications" / "INBOX.md"
