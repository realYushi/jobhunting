"""Smart scraping with date-window watermark and global dedup.

This module provides intelligent job listing aggregation:
- Fetches listings within a per-source date window (last_scrape watermark)
- Global deduplication across keywords within a single run
- Advances the per-source watermark only after a successful scrape
- Clear summary: "Found X total, Y within-run duplicates, Z new"
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable
from urllib.parse import quote, urlencode

from lib.harness_utils import load_script, parse_harness_json_output, run_harness
from lib.paths import tracker_path
from lib.scraper import JobListing, load_search_config
from lib.tracker import load_last_scrape, save_last_scrape


@dataclass(frozen=True)
class ScrapeSummary:
    """Summary of a scraping run."""

    total_found: int  # Total listings fetched
    duplicates_within_run: int  # Removed as duplicates across keywords
    new: int  # Listings returned after within-run dedup
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


def _unique_keywords(profiles: list[dict[str, Any]]) -> list[str]:
    """Return deduplicated non-empty keywords in first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for profile in profiles:
        for keyword in profile.get("keywords", []):
            cleaned = " ".join(str(keyword or "").split())
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
    return out


def within_days(posted: str | None, window: int) -> bool:
    """Return True if ``posted`` text describes a listing within ``window`` days.

    Fuzzy text formats recognised:
      today / new           → 0 days
      yesterday             → 1 day
      Nd / N day[s] ago     → N days
      N week[s] ago         → N * 7 days
      N month[s] ago        → N * 30 days
      YYYY-MM-DD            → calendar delta to today

    null / unparseable → True (keep the listing; act-on dedup handles repeats).
    """
    if not posted:
        return True
    text = " ".join(posted.strip().casefold().split())
    if text in {"today", "new"}:
        return True
    if text == "yesterday":
        return 1 <= window
    # "Nd" format (e.g. "3d")
    m = re.fullmatch(r"(\d+)d", text)
    if m:
        return int(m.group(1)) <= window
    # "N day(s) ago" / "N week(s) ago" / "N month(s) ago"
    m = re.fullmatch(r"(\d+)\s+(day|days|week|weeks|month|months)\s+ago", text)
    if m:
        value = int(m.group(1))
        unit = m.group(2).rstrip("s")
        if unit == "day":
            age = value
        elif unit == "week":
            age = value * 7
        else:
            age = value * 30
        return age <= window
    # ISO date "YYYY-MM-DD"
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            posted_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            age = (date.today() - posted_date).days
            return age <= window
        except ValueError:
            return True
    # Unparseable → keep
    return True


def smart_scrape(
    profiles: list[dict[str, Any]],
    max_total: int = 100,
    max_per_source: int = 50,
) -> tuple[list[JobListing], ScrapeSummary]:
    """Scrape jobs using a per-source date-window watermark.

    Args:
        profiles: List of search profiles with keywords, location, etc.
        max_total: Maximum total listings to return.
        max_per_source: Maximum listings per source.

    Returns:
        (listings, summary)

    The per-source ``last_scrape`` watermark in the sidecar ledger bounds how
    far back each source is fetched. After a source scrapes without raising,
    its watermark is advanced to today. Sources that error keep their old
    watermark so the gap is auto-covered on the next run.
    """
    config = load_search_config()
    defaults = config.get("defaults", {})
    buffer_days: int = int(defaults.get("scrape_buffer_days", 2))
    initial_lookback: int = int(defaults.get("scrape_initial_lookback_days", 31))

    today_str = date.today().isoformat()
    watermark = load_last_scrape(tracker_path())

    all_listings: list[JobListing] = []

    # Group profiles by source.
    source_profiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for profile in profiles:
        sources = profile.get("sources", ["linkedin", "seek"])
        for source in sources:
            source_profiles[source].append(profile)

    # Scrape each source with its computed window.
    updated_watermark = dict(watermark)
    for source, profs in source_profiles.items():
        if not profs:
            continue
        # Compute window for this source.
        last_str = watermark.get(source)
        if last_str:
            try:
                last_date = date.fromisoformat(last_str)
                days_since = (date.today() - last_date).days
            except ValueError:
                days_since = initial_lookback
        else:
            days_since = initial_lookback
        window = max(buffer_days, days_since + 1)

        print(
            f"\nScraping {source} (window={window}d)...",
            file=sys.stderr,
        )

        try:
            source_listings = _scrape_source(
                source,
                max_per_source,
                window,
                keywords=_unique_keywords(profs),
            )
            all_listings.extend(source_listings)
            # Advance watermark only on success.
            updated_watermark[source] = today_str
        except Exception as e:
            print(f"  {source} scrape error (watermark unchanged): {e}", file=sys.stderr)

    save_last_scrape(tracker_path(), updated_watermark)

    # Global dedup within this run.
    before_dedup = len(all_listings)
    unique_listings = dedup_within_run(all_listings)
    after_dedup = len(unique_listings)

    new_listings = unique_listings[:max_total]

    by_source: dict[str, int] = defaultdict(int)
    for lst in unique_listings:
        by_source[lst.source] += 1

    summary = ScrapeSummary(
        total_found=before_dedup,
        duplicates_within_run=before_dedup - after_dedup,
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
    window: int,
    *,
    first_page: int = 1,
    max_pages: int = 3,
    log_prefix: str | None = None,
    recent_filter: Callable[[str | None], bool] | None = None,
) -> list[JobListing]:
    """Generic per-URL paginator shared by URL-fixed sources.

    Pagination is bounded by ``max_pages`` per base URL; we stop early when a
    page returns no listings, when a ``recent_filter`` signals the page is
    entirely older than the window, or when the harness call fails.
    """
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
                load_script(script_name, url=url, page=page), timeout=120, source=source
            )
            if retcode != 0:
                break

            page_listings = _parse_jobs(stdout, source, recent_filter)
            if not page_listings:
                # No listings passed the recency filter — page is all-old; stop.
                if recent_filter is not None:
                    print(
                        f"  Page {page}: all listings older than window ({window}d), stopping",
                        file=sys.stderr,
                    )
                break

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
    window: int,
    *,
    keywords: list[str] | None = None,
) -> list[JobListing]:
    """Scrape a single source with date-window bounding."""
    source_keywords = _keywords_for_source(source, keywords or [])
    if source == "linkedin":
        listings = _scrape_paginated(
            "linkedin",
            tuple(_linkedin_base_urls(source_keywords, window)),
            "linkedin-list",
            lambda base, page: f"{base}&start={(page - 1) * 25}",
            max_results,
            window,
            log_prefix="LinkedIn base",
        )
        return [lst for lst in listings if _title_looks_software(lst.title)][:max_results]
    if source == "seek":
        return _scrape_paginated(
            "seek",
            tuple(_seek_base_urls(source_keywords, window)),
            "seek-list",
            _append_page_param,
            max_results,
            window,
            log_prefix="Seek base",
        )
    if source == "hiringcafe":
        return _scrape_hiringcafe_paginated(max_results, window)
    if source == "workingnomads":
        return _scrape_paginated(
            "workingnomads",
            (_WORKINGNOMADS_SEARCH_URL,),
            "workingnomads-list",
            _append_page_param,
            max_results,
            window,
            recent_filter=lambda p: within_days(p, window),
        )
    if source == "wellfound":
        return _scrape_wellfound_paginated(max_results, window, source_keywords)
    if source == "weworkremotely":
        return _scrape_weworkremotely(max_results, window, source_keywords)
    if source == "prosple":
        return _scrape_paginated(
            "prosple",
            tuple(_prosple_base_urls(source_keywords)),
            "prosple-list",
            _append_page_param,
            max_results,
            window,
            max_pages=1,
            log_prefix="Prosple base",
            recent_filter=lambda p: within_days(p, window),
        )
    print(f"  Unknown source: {source}", file=sys.stderr)
    return []


_DEFAULT_KEYWORDS: tuple[str, ...] = ("Software Engineer",)
_SOURCE_KEYWORD_ALLOWLISTS: dict[str, tuple[str, ...]] = {
    "linkedin": (
        "Software Engineer",
        "Software Developer",
        "Full Stack Engineer",
        "Full Stack Developer",
        "Frontend Engineer",
        "Frontend Developer",
        "Backend Engineer",
        "Backend Developer",
        "AI Engineer",
        "AI Application Engineer",
        "LLM Engineer",
        "Applied AI Engineer",
    ),
    "seek": (
        "Software Engineer",
        "Software Developer",
        "Full Stack Engineer",
        "Full Stack Developer",
        "Frontend Engineer",
        "Frontend Developer",
        "Backend Engineer",
        "Backend Developer",
        "AI Engineer",
        "LLM Engineer",
        "Applied AI Engineer",
    ),
    "weworkremotely": (
        "Software Engineer",
        "Software Developer",
        "Full Stack Engineer",
        "Full Stack Developer",
        "Frontend Engineer",
        "Backend Engineer",
        "AI Engineer",
        "LLM Engineer",
    ),
    "prosple": (
        "Software Engineer",
        "Software Developer",
        "Full Stack Engineer",
        "Full Stack Developer",
        "Frontend Engineer",
        "Frontend Developer",
        "Backend Engineer",
        "Backend Developer",
        "AI Engineer",
        "AI Application Engineer",
        "LLM Engineer",
        "Applied AI Engineer",
    ),
}
_SOFTWARE_TITLE_TERMS: tuple[str, ...] = (
    "software",
    "developer",
    "full stack",
    "frontend",
    "front-end",
    "backend",
    "back-end",
    "product engineer",
    "web engineer",
    "web developer",
    "application developer",
    "ai engineer",
    "llm",
    "machine learning",
    "applied ai",
)


def _keywords_for_source(source: str, keywords: list[str]) -> list[str]:
    allowed = _SOURCE_KEYWORD_ALLOWLISTS.get(source)
    if not allowed:
        return keywords or list(_DEFAULT_KEYWORDS)
    allowed_set = {item.casefold() for item in allowed}
    out = [keyword for keyword in keywords if keyword.casefold() in allowed_set]
    return out or list(allowed)


def _title_looks_software(title: str | None) -> bool:
    text = " ".join((title or "").casefold().split())
    return any(term in text for term in _SOFTWARE_TITLE_TERMS)


def _slugify_keyword(keyword: str) -> str:
    return "-".join(part for part in keyword.casefold().replace("/", " ").split() if part)


def _linkedin_base_urls(keywords: list[str], window_days: int = 31) -> list[str]:
    """Build LinkedIn search URLs filtered to ``window_days`` days.

    ``f_TPR=r{window_days * 86400}`` tells LinkedIn to return only listings
    posted within that many seconds of now.
    """
    tpr = f"r{window_days * 86400}"
    out: list[str] = []
    for keyword in (keywords or list(_DEFAULT_KEYWORDS)):
        # Auckland, full-time
        out.append(
            "https://www.linkedin.com/jobs/search"
            f"?keywords={quote(keyword)}"
            "&location=Auckland"
            "&geoId=100749476"
            "&distance=25"
            f"&f_TPR={tpr}"
            "&f_JT=F"
            "&f_E=2%2C3"
            "&f_PP=100749476"
            "&sortBy=DD"
        )
        # NZ-wide, remote only
        out.append(
            "https://www.linkedin.com/jobs/search"
            f"?keywords={quote(keyword)}"
            "&location=New%20Zealand"
            "&geoId=105490917"
            "&distance=0"
            f"&f_TPR={tpr}"
            "&f_WT=2"
            "&f_E=2%2C3"
            "&sortBy=DD"
        )
    return out


def _seek_daterange(window_days: int) -> int:
    """Map ``window_days`` to Seek's smallest supported daterange bucket (≥ window).

    Seek supports: 1, 3, 7, 14, 31. Capped at 31.
    """
    for bucket in (1, 3, 7, 14, 31):
        if bucket >= window_days:
            return bucket
    return 31


def _seek_base_urls(keywords: list[str], window_days: int = 31) -> list[str]:
    """Build Seek search URLs filtered to the smallest daterange bucket ≥ window_days."""
    daterange = _seek_daterange(window_days)
    out: list[str] = []
    for keyword in (keywords or list(_DEFAULT_KEYWORDS)):
        slug = "-".join(part for part in keyword.split() if part)
        out.extend(
            [
                (
                    f"https://nz.seek.com/{slug}-jobs-in-information-communication-technology"
                    "/in-All-Auckland/full-time"
                    f"?daterange={daterange}"
                    "&sortmode=ListedDate"
                    "&classification=6281"
                    "&subclassification=6287%2C6290"
                ),
                (
                    f"https://nz.seek.com/{slug}-jobs-in-information-communication-technology"
                    "/in-All-Auckland"
                    f"?daterange={daterange}"
                    "&sortmode=ListedDate"
                    "&classification=6281"
                    "&subclassification=6287%2C6290"
                    "&workarrangement=1%2C2"
                ),
                (
                    f"https://au.seek.com/{slug}-jobs-in-information-communication-technology"
                    "/in-All-Australia/remote"
                    "?sortmode=ListedDate"
                    "&classification=6281"
                    "&subclassification=6287%2C6290"
                ),
                (
                    f"https://nz.seek.com/{slug}-jobs-in-information-communication-technology"
                    "/in-All-New-Zealand/remote"
                    "?sortmode=ListedDate"
                    "&classification=6281"
                    "&subclassification=6287%2C6290"
                ),
            ]
        )
    return out


def _prosple_base_urls(keywords: list[str]) -> list[str]:
    out: list[str] = []
    for keyword in (keywords or list(_DEFAULT_KEYWORDS)):
        params = urlencode(
            {
                "location": "Auckland, AU, New Zealand",
                "sort": "newest_opportunities|desc",
                "opportunity_types": "1",
                "search_radius": "50",
                "keywords": keyword,
            }
        )
        out.append(f"https://nz.prosple.com/search-jobs?{params}")
    return out


_HIRINGCAFE_BASE_SEARCH_STATE: dict[str, Any] = {
    "departments": ["Software Development"],
    "seniorityLevel": ["No Prior Experience Required", "Entry Level"],
    "roleYoeRange": [0, 2],
    "sortBy": "date",
    # dateFetchedPastNDays is overridden at call time by _hiringcafe_page_url
    # to match the per-run window.
    "dateFetchedPastNDays": 31,
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


def _hiringcafe_page_url_for_window(window: int) -> Callable[[str, int], str]:
    """Return a page-URL builder that embeds ``dateFetchedPastNDays=window``.

    hiring.cafe accepts ``dateFetchedPastNDays`` in its searchState JSON, but its
    effect is unverified: the list scraper reads only the first viewport of cards
    and extracts no ``posted`` date, so live runs at window=1 vs window=31 return
    the same set. The within_days fallback is therefore a no-op here too. Tight
    date-bounding for hiring.cafe is a separate scraper-quality task; for now this
    source relies on downstream act-on dedup to avoid re-packaging.
    """
    import json as _json
    import urllib.parse

    def _build(_base: str, page: int) -> str:
        state = {**_HIRINGCAFE_BASE_SEARCH_STATE, "dateFetchedPastNDays": window, "page": page}
        encoded = urllib.parse.quote(_json.dumps(state, separators=(",", ":")))
        return f"https://hiring.cafe/?searchState={encoded}"

    return _build


def _scrape_hiringcafe_paginated(
    max_results: int,
    window: int,
) -> list[JobListing]:
    """Scrape hiring.cafe via searchState (Software Development, no-prior/entry-
    level, YOE 0-2, sorted by date, US/AU/NZ).

    ``window`` is passed as ``dateFetchedPastNDays`` but does not measurably bound
    results through this scraper (see ``_hiringcafe_page_url_for_window``); the
    source leans on downstream act-on dedup instead. Location eligibility is
    checked later against full JDs so globally remote roles are not lost just
    because a card shows a country/region.
    """
    return _scrape_paginated(
        "hiringcafe",
        ("",),  # base url is generated entirely from searchState
        "hiringcafe-list-paginated",
        _hiringcafe_page_url_for_window(window),
        max_results,
        window,
    )


_WORKINGNOMADS_SEARCH_URL = (
    "https://www.workingnomads.com/jobs"
    "?location=apac,north-america,europe"
    "&experienceLevel=entry-level"
    "&category=development"
    "&positionType=full-time"
)


_WELLFOUND_ROLE_ALIASES: dict[str, str] = {
    "software-engineer": "software-engineer",
    "software-developer": "software-engineer",
    "full-stack-engineer": "full-stack-developer",
    "full-stack-developer": "full-stack-developer",
    "frontend-engineer": "frontend-engineer",
    "frontend-developer": "frontend-engineer",
    "backend-engineer": "backend-developer",
    "backend-developer": "backend-developer",
    "web-engineer": "software-engineer",
    "application-developer": "software-engineer",
    "product-engineer": "software-engineer",
    "ai-engineer": "artificial-intelligence-engineer",
    "ai-application-engineer": "artificial-intelligence-engineer",
    "llm-engineer": "artificial-intelligence-engineer",
    "applied-ai-engineer": "artificial-intelligence-engineer",
    "machine-learning-engineer": "artificial-intelligence-engineer",
    "ai-native-engineer": "artificial-intelligence-engineer",
}
_WELLFOUND_FALLBACK_SLUGS: tuple[str, ...] = (
    "software-engineer",
    "full-stack-developer",
    "backend-developer",
    "frontend-engineer",
    "artificial-intelligence-engineer",
)


def _wellfound_base_urls(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for keyword in (keywords or list(_DEFAULT_KEYWORDS)):
        slug = _slugify_keyword(keyword)
        mapped = _WELLFOUND_ROLE_ALIASES.get(slug)
        if not mapped or mapped in seen:
            continue
        seen.add(mapped)
        out.append(f"https://wellfound.com/role/r/{mapped}")
    if out:
        return out
    return [f"https://wellfound.com/role/r/{slug}" for slug in _WELLFOUND_FALLBACK_SLUGS]


def _weworkremotely_search_url(keywords: list[str]) -> str:
    term = quote(" ".join(keywords[:3])) if keywords else ""
    return (
        "https://weworkremotely.com/remote-jobs/search"
        f"?search_uuid=&sort=&term={term}&categories_chosen="
        "&categories%5B%5D=2&categories%5B%5D=17&categories%5B%5D=18"
        "&countries_chosen=&chosen-salary_range=&skills_chosen="
    )


def _scrape_wellfound_paginated(
    max_results: int,
    window: int,
    keywords: list[str],
) -> list[JobListing]:
    """Scrape Wellfound remote startup engineering listings.

    Round-robins pages across role URLs so the first broad "software engineer"
    page does not consume the whole per-source cap before full-stack/backend/AI
    pages get a chance to contribute. Eligibility for US-only / region-locked
    roles is checked later against the full JD.
    """
    recent_filter = lambda p: within_days(p, window)  # noqa: E731
    listings: list[JobListing] = []

    for page in range(1, 3):
        for base_search_url in _wellfound_base_urls(keywords):
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

            page_listings = _parse_jobs(stdout, "wellfound", recent_filter)
            if not page_listings:
                print(
                    f"  Page {page}: all listings older than window ({window}d), stopping",
                    file=sys.stderr,
                )
                break

            listings.extend(page_listings)

    return listings[:max_results]


def _scrape_weworkremotely(
    max_results: int,
    window: int,
    keywords: list[str],
) -> list[JobListing]:
    """Scrape We Work Remotely programming search results (single page).

    WWR embeds all current search results in one page; postings are filtered
    locally against the date window via ``within_days``.
    """
    url = _weworkremotely_search_url(keywords)
    print(f"  We Work Remotely: {url[:60]}...", file=sys.stderr)
    stdout, _stderr, retcode = run_harness(
        load_script(
            "weworkremotely-list", url=url, page=1
        ),
        timeout=120,
    )
    if retcode != 0:
        return []

    listings = _parse_jobs(stdout, "weworkremotely", lambda p: within_days(p, window))
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
    print(f"  🆕 New listings: {summary.new}", file=sys.stderr)
    print(f"  By source: {summary.by_source}", file=sys.stderr)
