"""Smart scraping with fetch-until-overlap and global dedup.

This module provides intelligent job listing aggregation:
- Fetches across multiple keywords
- Stops when reaching already-seen jobs (overlap)
- Global deduplication across keywords
- Clear summary: "Found X total, Y already seen, Z new"
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from lib.harness_utils import load_script, parse_harness_json_output, run_harness
from lib.identity import ManualKey
from lib.paths import tracker_path
from lib.scraper import JobListing
from lib.tracker import (
    is_seen_key,
    is_skipped_key,
    load_tracker,
    mark_seen_key,
    save_tracker,
    seen_by_source,
)


@dataclass(frozen=True)
class ScrapeSummary:
    """Summary of a scraping run."""

    total_found: int  # Total listings fetched
    duplicates_within_run: int  # Removed as duplicates across keywords
    already_seen: int  # Seen in previous runs
    skipped: int  # Explicitly skipped by user
    new: int  # Actually new listings
    by_source: dict[str, int]  # Breakdown by source


def dedup_within_run(listings: list[JobListing]) -> list[JobListing]:
    """Remove duplicates within a single run (across keywords/sources).

    Uses (job_id, source) as the unique key since job_id might collide across sources.
    """
    seen = set()
    unique = []
    for lst in listings:
        key = (lst.job_id, lst.source)
        if key not in seen:
            seen.add(key)
            unique.append(lst)
    return unique


def smart_scrape(
    profiles: list[dict[str, Any]],
    max_total: int = 100,
    max_per_source: int = 50,
    stop_at_overlap: bool = True,
) -> tuple[list[JobListing], ScrapeSummary]:
    """Scrape jobs with intelligent dedup and overlap detection.

    Args:
        profiles: List of search profiles with keywords, location, etc.
        max_total: Maximum total listings to return
        max_per_source: Maximum listings per source (LinkedIn, Seek, etc.)
        stop_at_overlap: If True, stop fetching when hitting already-seen jobs

    Returns:
        (listings, summary)
    """
    tracker = load_tracker(tracker_path())
    # Paginators want O(1) "is id from source X seen?" — rebucket the flat
    # seen list into {source: {id, ...}} for them.
    seen_jobs = seen_by_source(tracker)

    all_listings: list[JobListing] = []

    # Group profiles by source so we know which sources to scrape.
    source_profiles = defaultdict(list)
    for profile in profiles:
        sources = profile.get("sources", ["linkedin", "seek"])
        for source in sources:
            source_profiles[source].append(profile)

    # Scrape each source. All current sources have URL-fixed search params,
    # so per-profile keywords/location don't influence the scrape — we run
    # one pass per source regardless of how many profiles target it.
    for source, profs in source_profiles.items():
        if not profs:
            continue
        print(f"\nScraping {source}...", file=sys.stderr)

        source_listings = _scrape_source(
            source,
            max_per_source,
            seen_jobs if stop_at_overlap else None,
        )
        all_listings.extend(source_listings)

        if stop_at_overlap and source_listings:
            recent = source_listings[-min(5, len(source_listings)) :]
            if all(is_seen_key(tracker, lst.key) for lst in recent):
                print(
                    "  Reached overlap point, stopping pagination", file=sys.stderr
                )

    # Global dedup within this run
    before_dedup = len(all_listings)
    unique_listings = dedup_within_run(all_listings)
    after_dedup = len(unique_listings)

    # Filter by seen_jobs, skipped_jobs, and board-level applied markers.
    new_listings = []
    seen_count = 0
    skipped_count = 0
    for lst in unique_listings[:max_total]:
        manual = ManualKey(company_lc=lst.company, position_lc=lst.title)
        snippet = lst.snippet or ""
        already_applied = any(
            line.strip().lower() == "applied" for line in snippet.splitlines()
        )
        if is_seen_key(tracker, lst.key) or already_applied:
            seen_count += 1
            mark_seen_key(tracker, lst.key)
        elif is_skipped_key(tracker, lst.key, fallback=manual):
            skipped_count += 1
        else:
            new_listings.append(lst)
            mark_seen_key(tracker, lst.key)

    # Save updated tracker
    save_tracker(tracker_path(), tracker)

    # Build summary
    by_source = defaultdict(int)
    for lst in unique_listings:
        by_source[lst.source] += 1

    summary = ScrapeSummary(
        total_found=before_dedup,
        duplicates_within_run=before_dedup - after_dedup,
        already_seen=seen_count,
        skipped=skipped_count,
        new=len(new_listings),
        by_source=dict(by_source),
    )

    return new_listings, summary


def _parse_jobs(
    stdout: str,
    source: str,
    recent_filter: Callable[[str | None], bool] | None = None,
) -> list[JobListing]:
    """Build JobListings from one harness run's stdout.

    `recent_filter` (when supplied) drops postings whose `posted` text fails
    the source-specific recency check (wellfound, weworkremotely).
    """
    out: list[JobListing] = []
    for data in parse_harness_json_output(stdout):
        if "jobs" not in data:
            continue
        for job in data["jobs"]:
            job_id = job.get("job_id")
            if not job_id:
                continue
            if recent_filter is not None and not recent_filter(job.get("posted")):
                continue
            out.append(
                JobListing(
                    job_id=str(job_id),
                    source=source,
                    url=job["url"],
                    title=job.get("title") or "Unknown",
                    company=job.get("company") or "Unknown",
                    snippet=job.get("snippet", ""),
                    posted=job.get("posted"),
                    location=job.get("location") or None,
                )
            )
    return out


def _scrape_paginated(
    source: str,
    base_urls: tuple[str, ...],
    script_name: str,
    page_url: Callable[[str, int], str],
    max_results: int,
    seen_jobs: dict[str, set[str]] | None,
    *,
    first_page: int = 1,
    max_pages: int = 3,
    log_prefix: str | None = None,
    recent_filter: Callable[[str | None], bool] | None = None,
) -> list[JobListing]:
    """Generic per-URL paginator shared by URL-fixed sources.

    Pagination is bounded by `max_pages` per base URL; we stop early when a
    page returns no listings, when every listing on a page has been seen
    before (overlap), or when the harness call fails.
    """
    seen = seen_jobs.get(source, set()) if seen_jobs else set()
    listings: list[JobListing] = []

    for base_url in base_urls:
        if len(listings) >= max_results:
            break
        if log_prefix:
            print(f"  {log_prefix}: {base_url[:60]}...", file=sys.stderr)

        for page_offset in range(max_pages):
            if len(listings) >= max_results:
                break
            page = first_page + page_offset
            url = page_url(base_url, page)
            stdout, _stderr, retcode = run_harness(
                load_script(script_name, url=url, page=page), timeout=120
            )
            if retcode != 0:
                break

            page_listings = _parse_jobs(stdout, source, recent_filter)
            if not page_listings:
                break

            if seen:
                new_in_page = [j for j in page_listings if j.job_id not in seen]
                if not new_in_page:
                    print(
                        f"  Page {page}: all jobs already seen, stopping",
                        file=sys.stderr,
                    )
                    break
                listings.extend(new_in_page)
            else:
                listings.extend(page_listings)

    return listings[:max_results]


def _append_page_param(base: str, page: int) -> str:
    """Add `page=N` with the right separator; preserves the base URL when page == 1."""
    if page == 1:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}page={page}"


def _scrape_source(
    source: str,
    max_results: int,
    seen_jobs: dict[str, set[str]] | None,
) -> list[JobListing]:
    """Scrape a single source with pagination support.

    If seen_jobs is provided, stops when reaching overlap.
    """
    if source == "linkedin":
        return _scrape_paginated(
            "linkedin",
            _LINKEDIN_BASE_URLS,
            "linkedin-list",
            lambda base, page: f"{base}&start={(page - 1) * 25}",
            max_results,
            seen_jobs,
            log_prefix="LinkedIn base",
        )
    if source == "seek":
        return _scrape_paginated(
            "seek",
            _SEEK_BASE_URLS,
            "seek-list",
            _append_page_param,
            max_results,
            seen_jobs,
            log_prefix="Seek base",
        )
    if source == "hiringcafe":
        return _scrape_hiringcafe_paginated(max_results, seen_jobs)
    if source == "workingnomads":
        return _scrape_paginated(
            "workingnomads",
            (_WORKINGNOMADS_SEARCH_URL,),
            "workingnomads-list",
            _append_page_param,
            max_results,
            seen_jobs,
        )
    if source == "wellfound":
        return _scrape_wellfound_paginated(max_results, seen_jobs)
    if source == "weworkremotely":
        return _scrape_weworkremotely(max_results, seen_jobs)
    print(f"  Unknown source: {source}", file=sys.stderr)
    return []


_LINKEDIN_BASE_URLS: tuple[str, ...] = (
    # Auckland — Software Engineer, entry/associate level, full-time, last 30 days.
    "https://www.linkedin.com/jobs/search"
    "?keywords=Software%20Engineer"
    "&location=Auckland"
    "&geoId=100749476"
    "&distance=25"
    "&f_TPR=r2592000"
    "&f_JT=F"
    "&f_E=2%2C3"
    "&f_PP=100749476"
    "&sortBy=DD",
)


_SEEK_BASE_URLS: tuple[str, ...] = (
    # Auckland (NZ) — Developer jobs, ICT classifications, last 31 days,
    # subclassifications 6287+6302 (Developers/Programmers + Eng - Software),
    # work arrangement 1+2 (remote + hybrid).
    "https://nz.seek.com/Developer-jobs/in-All-Auckland"
    "?classification=6281%2C1209"
    "&daterange=31"
    "&sortmode=ListedDate"
    "&subclassification=6287%2C6302"
    "&workarrangement=1%2C2",
    # Australia — Developer jobs in ICT, remote only.
    "https://au.seek.com/Developer-jobs-in-information-communication-technology"
    "/in-All-Australia/remote"
    "?sortmode=ListedDate"
    "&subclassification=6287%2C6302",
)


_HIRINGCAFE_BASE_SEARCH_STATE: dict[str, Any] = {
    "departments": ["Software Development"],
    "seniorityLevel": ["No Prior Experience Required", "Entry Level"],
    "roleYoeRange": [0, 2],
    "sortBy": "date",
    "dateFetchedPastNDays": 61,
    "locations": [
        {
            "id": "FxY1yZQBoEtHp_8UEq7V",
            "types": ["country"],
            "address_components": [
                {"long_name": "United States", "short_name": "US", "types": ["country"]},
            ],
            "formatted_address": "United States",
            "population": 327167434,
            "workplace_types": ["Remote"],
            "options": {"flexible_regions": []},
        },
        {
            "id": "LBY1yZQBoEtHp_8UEq3V",
            "types": ["continent"],
            "address_components": [
                {
                    "long_name": "Australia",
                    "short_name": "Australia",
                    "types": ["continent"],
                },
            ],
            "formatted_address": "Australia / Oceania",
            "population": 42000000,
            "workplace_types": ["Remote"],
            "options": {"flexible_regions": []},
        },
        {
            "id": "wxY1yZQBoEtHp_8UErfX",
            "types": ["administrative_area_level_1"],
            "address_components": [
                {
                    "long_name": "Auckland",
                    "short_name": "E7",
                    "types": ["administrative_area_level_1"],
                },
                {"long_name": "New Zealand", "short_name": "NZ", "types": ["country"]},
            ],
            "formatted_address": "Auckland, New Zealand",
            "population": 1798300,
            "workplace_types": ["Onsite", "Hybrid"],
            "options": {
                "flexible_regions": ["anywhere_in_country", "anywhere_in_continent"]
            },
        },
    ],
}


def _hiringcafe_page_url(_base: str, page: int) -> str:
    """Build hiring.cafe URL by encoding the page number into searchState JSON."""
    import json as _json
    import urllib.parse

    state = {**_HIRINGCAFE_BASE_SEARCH_STATE, "page": page}
    encoded = urllib.parse.quote(_json.dumps(state, separators=(",", ":")))
    return f"https://hiring.cafe/?searchState={encoded}"


def _scrape_hiringcafe_paginated(
    max_results: int,
    seen_jobs: dict[str, set[str]] | None,
) -> list[JobListing]:
    """Scrape hiring.cafe with pagination and overlap detection.

    Uses a fixed searchState (Software Development, no-prior/entry-level,
    YOE 0-2, last 61 days, sorted by date, US/AU/NZ). Location eligibility is
    checked later against full JDs so globally remote roles are not lost just
    because a card shows a country/region.
    """
    return _scrape_paginated(
        "hiringcafe",
        ("",),  # base url is generated entirely from searchState
        "hiringcafe-list-paginated",
        _hiringcafe_page_url,
        max_results,
        seen_jobs,
    )


_WORKINGNOMADS_SEARCH_URL = (
    "https://www.workingnomads.com/jobs"
    "?location=apac,north-america,europe"
    "&experienceLevel=entry-level"
    "&category=development"
    "&positionType=full-time"
)


def _is_wellfound_recent(posted: str | None) -> bool:
    """Return True for Wellfound postings less than about one month old."""
    if not posted:
        return False

    text = " ".join(posted.casefold().split())
    if text in {"today", "yesterday"}:
        return True

    parts = text.split()
    if len(parts) < 3 or parts[-1] != "ago":
        return False

    try:
        value = int(parts[0])
    except ValueError:
        return False

    unit = parts[1].rstrip("s")
    if unit == "day":
        return value <= 31
    if unit == "week":
        return value <= 4
    return False


def _is_weworkremotely_recent(posted: str | None) -> bool:
    """Return True for WWR postings less than about one month old."""
    if not posted:
        return False
    text = " ".join(posted.casefold().split())
    if text in {"new", "today"}:
        return True
    if text.endswith("d"):
        try:
            return int(text[:-1]) <= 31
        except ValueError:
            return False
    return False


_WELLFOUND_BASE_URLS: tuple[str, ...] = (
    "https://wellfound.com/role/r/software-engineer",
    "https://wellfound.com/role/r/full-stack-developer",
    "https://wellfound.com/role/r/backend-developer",
    "https://wellfound.com/role/r/frontend-engineer",
    "https://wellfound.com/role/r/artificial-intelligence-engineer",
)


def _scrape_wellfound_paginated(
    max_results: int,
    seen_jobs: dict[str, set[str]] | None,
) -> list[JobListing]:
    """Scrape Wellfound remote startup engineering listings.

    Round-robins pages across role URLs so the first broad "software engineer"
    page does not consume the whole per-source cap before full-stack/backend/AI
    pages get a chance to contribute. Eligibility for US-only / region-locked
    roles is checked later against the full JD.
    """
    seen = seen_jobs.get("wellfound", set()) if seen_jobs else set()
    listings: list[JobListing] = []

    for page in range(1, 3):
        for base_search_url in _WELLFOUND_BASE_URLS:
            if len(listings) >= max_results:
                break
            print(
                f"  Wellfound base: {base_search_url[:60]}... page {page}",
                file=sys.stderr,
            )
            url = _append_page_param(base_search_url, page)
            stdout, _stderr, retcode = run_harness(
                load_script("wellfound-list", url=url, page=page), timeout=120
            )
            if retcode != 0:
                continue

            page_listings = _parse_jobs(stdout, "wellfound", _is_wellfound_recent)
            if not page_listings:
                break

            if seen:
                new_in_page = [j for j in page_listings if j.job_id not in seen]
                if not new_in_page:
                    print(
                        f"  Page {page}: all jobs already seen, stopping",
                        file=sys.stderr,
                    )
                    break
                listings.extend(new_in_page)
            else:
                listings.extend(page_listings)

    return listings[:max_results]


_WEWORKREMOTELY_SEARCH_URL = (
    "https://weworkremotely.com/remote-jobs/search"
    "?search_uuid=&sort=&term=&categories_chosen="
    "&categories%5B%5D=2&categories%5B%5D=17&categories%5B%5D=18"
    "&countries_chosen=&chosen-salary_range=&skills_chosen="
)


def _scrape_weworkremotely(
    max_results: int,
    seen_jobs: dict[str, set[str]] | None,
) -> list[JobListing]:
    """Scrape We Work Remotely programming search results (single page).

    WWR embeds all current search results in one page; postings older than one
    month are filtered locally from the visible age label.
    """
    seen = seen_jobs.get("weworkremotely", set()) if seen_jobs else set()
    print(f"  We Work Remotely: {_WEWORKREMOTELY_SEARCH_URL[:60]}...", file=sys.stderr)
    stdout, _stderr, retcode = run_harness(
        load_script(
            "weworkremotely-list", url=_WEWORKREMOTELY_SEARCH_URL, page=1
        ),
        timeout=120,
    )
    if retcode != 0:
        return []

    listings = _parse_jobs(stdout, "weworkremotely", _is_weworkremotely_recent)
    if seen:
        listings = [j for j in listings if j.job_id not in seen]
    return listings[:max_results]


def print_summary(summary: ScrapeSummary) -> None:
    """Print a human-readable summary."""
    print("\n📊 Scrape Summary:", file=sys.stderr)
    print(f"  Total listings fetched: {summary.total_found}", file=sys.stderr)
    if summary.duplicates_within_run > 0:
        print(
            f"  Duplicates removed (cross-keyword): {summary.duplicates_within_run}",
            file=sys.stderr,
        )
    print(f"  Already seen (previous runs): {summary.already_seen}", file=sys.stderr)
    if summary.skipped > 0:
        print(
            f"  Skipped (user marked not interested): {summary.skipped}",
            file=sys.stderr,
        )
    print(f"  🆕 New listings: {summary.new}", file=sys.stderr)
    print(f"  By source: {summary.by_source}", file=sys.stderr)
