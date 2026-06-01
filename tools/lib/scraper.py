"""Job scraper utilities.

Uses browser-harness to extract listings from LinkedIn and Seek.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .identity import BoardKey
from .paths import project_root


@dataclass(frozen=True)
class JobListing:
    """A job listing from a source site."""

    job_id: str
    source: str
    url: str
    title: str
    company: str
    snippet: str
    posted: str | None = None
    location: str | None = None

    @property
    def key(self) -> BoardKey:
        """Stable cross-run identity for dedup against the tracker."""
        return BoardKey(source=self.source, job_id=self.job_id)


def load_search_config() -> dict[str, Any]:
    """Load search-config.json."""
    config_path = project_root() / "tools" / "search-config.json"
    with open(config_path) as f:
        return json.load(f)


def extract_linkedin_job_id(url: str) -> str | None:
    """Extract job ID from LinkedIn URL."""
    # LinkedIn URLs can be:
    # - /jobs/view/<id>/
    # - /jobs/search/?currentJobId=<id>
    match = re.search(r"(?:currentJobId=|/jobs/view/)(\d+)", url)
    return match.group(1) if match else None


def extract_seek_job_id(url: str) -> str | None:
    """Extract job slug from Seek URL."""
    # Seek URLs are like: /job/<slug>?...
    match = re.search(r"/job/([^/?]+)", url)
    return match.group(1) if match else None
