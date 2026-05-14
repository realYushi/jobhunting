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


def company_dir(root: Path, company: str) -> Path:
    """Return the active application directory for a company."""
    safe = re.sub(r"[^a-zA-Z0-9._ -]+", "", company).strip() or slugify(company)
    return root / "applications" / "active" / safe


def templates_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "templates"


def base_resume_path(root: Path | None = None) -> Path:
    return templates_dir(root) / "base-resume.json"


def tracker_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "applications" / "application-tracker.json"
