"""Cheap pre-LLM filters: title/company hard-drops and the location gate.

These run before (and instead of) spending JD-fetch or scoring budget on
obviously-ineligible listings. They operate on the same ``source`` / ``title`` /
``company`` / ``snippet`` attributes exposed by both ``JobListing`` (scrape time)
and ``ScoreResult`` (package time), so the same helpers serve both stages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.scorer import ScoreResult
    from lib.scraper import JobListing


STRICT_OUTSIDE_LOCATION_PHRASES = (
    "live in europe or the us",
    "must be currently and legally authorized to work in the united states",
    "authorized to work in the united states",
    "remote us position",
    "outside of the u.s. will not",
    "outside of the us will not",
    "no visa sponsorship",
    "no non-us remote",
    "usa only",
    "us only",
    "u.s. only",
    "united states only",
)

GLOBAL_REMOTE_PHRASES = (
    "globally remote",
    "remote globally",
    "work from anywhere",
    "work remotely from anywhere",
    "100% remote position",
    "executed globally",
    "global remote",
    "location: anywhere",
    "anywhere in the world",
    "fully distributed",
)

ALLOWED_LOCATION_PHRASES = (
    "auckland",
    "new zealand",
    "australia",
    "apac",
    "asia pacific",
    "oceania",
    "anywhere",
)

OUTSIDE_LOCATION_PHRASES = (
    "united states",
    " usa",
    " us ",
    " u.s.",
    "canada",
    "united kingdom",
    " uk",
    "ireland",
    "europe",
    "emea",
    "north america",
    "latin america",
    "poland",
    "germany",
    "bulgaria",
    "spain",
    "portugal",
    "romania",
    "hungary",
    "estonia",
)


_PRE_FILTER_SOURCES = frozenset({"hiringcafe", "workingnomads", "wellfound", "weworkremotely"})

HARD_DROP_TITLE_PATTERNS = (
    "senior",
    "lead",
    "principal",
    "staff",
    "architect",
    "manager",
    "head of",
    "founding engineer",
    "qa",
    "quality assurance",
    "test engineer",
    "sdet",
    "devops",
    "site reliability",
    "sre",
    "platform engineer",
    "network engineer",
    "security engineer",
)

HARD_DROP_COMPANY_PATTERNS = (
    "dataannotation",
    "twine",
)


def _title_hard_drop_reason(listing: "JobListing") -> str | None:
    """Return a conservative prefetch drop reason from the title alone.

    This keeps obvious rubric hard-drops from consuming JD-fetch/scoring budget.
    The list is intentionally narrow: only strong seniority/off-track signals.
    """
    title = " ".join((listing.title or "").casefold().split())
    if not title:
        return None
    for pattern in HARD_DROP_TITLE_PATTERNS:
        if pattern in title:
            return f"title hard-drop: {pattern}"
    return None


def _company_hard_drop_reason(listing: "JobListing") -> str | None:
    """Return a drop reason if the company matches a blocked pattern."""
    company = (listing.company or "").casefold().strip()
    if not company:
        return None
    for pattern in HARD_DROP_COMPANY_PATTERNS:
        if pattern in company:
            return f"company hard-drop: {pattern}"
    return None


def _snippet_location_excluded(listing: "JobListing") -> bool:
    """True when a listing's snippet contains a hard location exclusion phrase.

    Conservative pre-LLM filter: only drops on STRICT phrases (e.g. "US only",
    "authorized to work in the US"). Softer signals stay for the full-JD check
    so we don't drop globally-remote roles whose card text happens to mention
    a region. Limited to the four sources that mix remote/region-locked roles.
    """
    if listing.source not in _PRE_FILTER_SOURCES:
        return False
    snippet = listing.snippet or ""
    if not snippet:
        return False
    text = " ".join(snippet.casefold().split())
    return any(phrase in text for phrase in STRICT_OUTSIDE_LOCATION_PHRASES)


def _location_eligibility(item: "ScoreResult", jd_text: str) -> tuple[bool, str | None]:
    """Return whether a listing should be packaged under the location rule.

    Keep globally/anywhere remote roles and Auckland/NZ/AU/APAC-friendly roles.
    Skip roles explicitly limited outside those regions unless the full JD says
    they can be done globally/from anywhere.
    """
    if item.source not in {"hiringcafe", "workingnomads", "wellfound", "weworkremotely"}:
        return True, None

    text = " ".join(jd_text.casefold().split())
    if any(phrase in text for phrase in STRICT_OUTSIDE_LOCATION_PHRASES):
        return False, "explicit location/work-authorization limit outside Auckland/NZ/AU/APAC"
    if any(phrase in text for phrase in GLOBAL_REMOTE_PHRASES):
        return True, None
    if any(phrase in text for phrase in ALLOWED_LOCATION_PHRASES):
        return True, None
    if any(phrase in text for phrase in OUTSIDE_LOCATION_PHRASES):
        return False, "location-limited outside Auckland/NZ/AU/APAC and not globally remote"
    return True, None
