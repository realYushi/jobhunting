"""Job research pipeline orchestrator.

Run: "python tools/pipeline.py"

This runs the full pipeline:
1. Reconcile INBOX (archive submitted/skipped)
2. Scrape LinkedIn + Seek for each configured profile
3. Stage-1 match score on listing snippets → drop below cutoff
4. Stage-2: generate CV + cover letter for top N matches
5. Append rows to INBOX.md, report counts
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib.harness_utils import load_script, run_harness
from lib.identity import BoardKey, JobKey, ManualKey, _norm_manual_field, try_manual_key
from lib.inbox import InboxRow, write_inbox_rows
from lib.paths import company_dirname, inbox_path as default_inbox, project_root
from lib.reconcile import InboxItem, parse_inbox, reconcile
from lib.tracker import key_for_app_dict, load_keyset, load_tracker
from lib.scorer import (
    ScoreResult,
    candidate_summary,
    filter_by_score,
    load_candidate_profile,
    score_listings,
    sort_by_score,
)
from lib.scraper import JobListing, load_search_config
from lib.smart_scrape import ScrapeSummary, print_summary, smart_scrape
from lib.workflow import WorkflowOptions, create_application_package


def _resolve_apply_url(item: ScoreResult) -> str | None:
    """Resolve source-board URLs to direct employer apply URLs where cheap."""
    if item.source != "workingnomads" or not item.job_id:
        return item.url
    try:
        req = urllib.request.Request(
            f"https://www.workingnomads.com/job/go/{item.job_id}/",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except Exception:
        return item.url


def _fetch_full_jd(url: str) -> str:
    """Fetch the full job description from a listing URL.

    Uses browser-harness with new_tab so concurrent callers each get an
    isolated tab; safe to invoke from a ThreadPoolExecutor.
    """
    # hiring.cafe needs a tab click to reveal the full JD
    pre_extract = ""
    if "hiring.cafe/viewjob" in url or "hiring.cafe/job" in url:
        pre_extract = r'''
js(r"""
(() => {
  const tabs = Array.from(document.querySelectorAll('button, a'))
    .filter(el => (el.innerText||'').trim() === 'Job Description');
  if (tabs.length) tabs[0].click();
})()
""")
wait(2)
'''
    stdout, stderr, retcode = run_harness(
        load_script("jd-fetch", url=url, pre_extract=pre_extract), timeout=60
    )
    if retcode != 0:
        return f"# Failed to fetch JD from {url}\n\nError: {stderr}"

    from lib.harness_utils import parse_harness_json_output

    results = parse_harness_json_output(stdout)
    if results and "jd" in results[0]:
        return results[0]["jd"]

    return f"# Could not extract JD from {url}"


JD_FETCH_PARALLELISM = 3


def _fetch_jds_parallel(
    items: list[ScoreResult], max_workers: int = JD_FETCH_PARALLELISM
) -> dict[str, str]:
    """Fetch JDs for many listings concurrently. Keyed by item.url.

    Each fetch opens its own tab in the user's Chrome via new_tab, so workers
    don't clobber each other. Failures fall back to a placeholder string, the
    same shape `_fetch_full_jd` returns on its own error path.
    """
    urls = [item.url for item in items if item.url]
    if not urls:
        return {}

    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_full_jd, url): url for url in urls}
        for fut in futures:
            url = futures[fut]
            try:
                out[url] = fut.result()
            except Exception as e:
                out[url] = f"# Failed to fetch JD from {url}\n\nError: {e}"
    return out


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


def _location_eligibility(item: ScoreResult, jd_text: str) -> tuple[bool, str | None]:
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


def _resolve_config(
    profiles: list[str] | None,
    sources: list[str] | None,
    score_cutoff: int | None,
    per_run_cap: int | None,
) -> tuple[list[dict], list[str], int, int]:
    """Resolve search profiles + defaults from search-config.json."""
    config = load_search_config()
    if profiles is None:
        profiles = [p["name"] for p in config["profiles"]]
    if sources is None:
        sources = config.get("defaults", {}).get("sources", ["linkedin", "seek"])

    cutoff = score_cutoff or config.get("defaults", {}).get("score_cutoff", 65)
    cap = per_run_cap or config.get("defaults", {}).get("per_run_cap", 10)

    profile_configs = []
    for name in profiles:
        for p in config["profiles"]:
            if p["name"] == name:
                p = {**p, "sources": sources}
                profile_configs.append(p)
                break

    return profile_configs, sources, cutoff, cap


def do_reconcile_and_scrape(
    root: Path,
    profile_configs: list[dict],
    dry_run: bool,
    reconcile_inbox: bool = True,
) -> list[JobListing]:
    """Phases 1-2: reconcile INBOX, then scrape sources."""
    if reconcile_inbox:
        print("🔄 Phase 1: Reconciling INBOX...", file=sys.stderr)
        inbox = default_inbox(root)
        result = reconcile(root, inbox_path=inbox, dry_run=dry_run)
        print(
            f"  Submitted: {len(result.submitted)}, Skipped: {len(result.skipped)},"
            f" Kept: {len(result.kept)}, Cleaned active dirs: {len(result.cleaned_active)}",
            file=sys.stderr,
        )
        for cleaned in result.cleaned_active:
            print(f"  🧹 {cleaned}", file=sys.stderr)
        for error in result.errors:
            print(f"  ⚠️ Reconcile cleanup issue: {error}", file=sys.stderr)
    else:
        print("🔄 Phase 1: Skipping INBOX reconcile (--no-reconcile)", file=sys.stderr)

    print("\n🔍 Phase 2: Scraping job listings...", file=sys.stderr)
    all_listings: list[JobListing] = []
    scrape_summary: ScrapeSummary | None = None
    try:
        all_listings, scrape_summary = smart_scrape(
            profiles=profile_configs,
            max_total=100,
            stop_at_overlap=True,
        )
        if scrape_summary:
            print_summary(scrape_summary)
    except Exception as e:
        print(f"  Scraping failed: {e}", file=sys.stderr)
        print("  Continuing with empty listing set...", file=sys.stderr)

    print(f"  Total listings to score: {len(all_listings)}", file=sys.stderr)
    return all_listings


COVER_QUEUE_PATH = Path("/tmp/jobhunting-cover-queue.json")


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


# Mirrors tracker.BUCKETS, ordered so the most-actionable status wins when a
# key appears in multiple buckets. Keep in sync with tracker.BUCKETS — any
# bucket not listed here still gets picked up via the sorted-keys fallback in
# _build_application_key_index, just at lower priority.
_BUCKET_PRIORITY: tuple[str, ...] = (
    "active",
    "interviews",
    "offers",
    "rejected",
    "withdrawn",
)


def _build_application_key_index(tracker: dict) -> dict[JobKey, dict]:
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
    items: list[InboxItem],
) -> tuple[dict[JobKey, InboxItem], dict[tuple[str, str], list[InboxItem]]]:
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


def _score_board_key(item: ScoreResult) -> BoardKey | None:
    # Strip before truthiness — BoardKey.__post_init__ checks non-empty BEFORE
    # stripping, so a whitespace-only id would slip past it and collapse to ''.
    source = (item.source or "").strip()
    job_id = str(item.job_id or "").strip()
    if not source or not job_id:
        return None
    return BoardKey(source=source, job_id=job_id)


_MANUAL_KEY_SENTINELS: frozenset[str] = frozenset({"", "unknown"})


def _score_manual_key(item: ScoreResult) -> ManualKey | None:
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
    index: dict[tuple[str, str], list[dict]], item: ScoreResult
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
    item: ScoreResult,
    *,
    application_key_index: dict[JobKey, dict],
    company_title_index: dict[tuple[str, str], list[dict]],
    inbox_key_index: dict[JobKey, InboxItem],
    inbox_company_title_index: dict[tuple[str, str], list[InboxItem]],
    skipped_set: set[JobKey],
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


def _is_cover_warning(warning: str) -> bool:
    """A warning is cover-letter related if it mentions placeholders or 'Cover letter'."""
    return "placeholder" in warning.lower() or "cover letter" in warning.lower()


def do_package_from_scores(
    root: Path,
    passed: list[ScoreResult],
    cap: int,
    dry_run: bool,
    fetch_jd: bool,
    skip_reconcile: bool = False,
) -> None:
    """Phases 4-5: build packages and write INBOX.

    Pass ``skip_reconcile=True`` when the caller has already reconciled INBOX
    in this same process (e.g. the inline `run_pipeline` flow) to avoid a
    redundant second pass through `cleanup_active_folder`.
    """
    inbox = default_inbox(root)
    print("\n📦 Phase 4: Creating application packages...", file=sys.stderr)

    if not skip_reconcile:
        # Package-only runs may happen after the user has marked INBOX rows as
        # submitted/skipped. Reconcile here too so duplicate checks see the
        # latest submitted statuses and skipped keyset before CV/cover gen.
        reconcile_result = reconcile(root, inbox_path=inbox, dry_run=dry_run)
        if reconcile_result.submitted or reconcile_result.skipped:
            print(
                "  Reconciled INBOX before packaging: "
                f"submitted={len(reconcile_result.submitted)}, "
                f"skipped={len(reconcile_result.skipped)}",
                file=sys.stderr,
            )
        for error in reconcile_result.errors:
            print(f"  ⚠️ Reconcile issue before packaging: {error}", file=sys.stderr)

    tracker = load_tracker(root / "applications" / "application-tracker.json")
    skipped_set = load_keyset(tracker, "skipped")
    application_key_index = _build_application_key_index(tracker)
    company_title_index = _build_company_title_index(tracker)
    inbox_key_index, inbox_company_title_index = _build_inbox_indexes(
        parse_inbox(inbox)
    )
    to_package: list[ScoreResult] = []
    for item in passed:
        duplicate_reason = _duplicate_reason(
            item,
            application_key_index=application_key_index,
            company_title_index=company_title_index,
            inbox_key_index=inbox_key_index,
            inbox_company_title_index=inbox_company_title_index,
            skipped_set=skipped_set,
        )
        if duplicate_reason:
            print(
                "  ⏭️  Skipping duplicate: "
                f"{item.title} @ {item.company} ({duplicate_reason})",
                file=sys.stderr,
            )
            continue
        to_package.append(item)
        if len(to_package) >= cap:
            break
    print(f"  Creating {len(to_package)} packages (cap: {cap})", file=sys.stderr)

    # Pre-fetch JDs in parallel (skip in dry-run since we don't build packages).
    jd_cache: dict[str, str] = {}
    if fetch_jd and not dry_run and to_package:
        print(
            f"  Fetching {len(to_package)} JDs in parallel "
            f"(workers={JD_FETCH_PARALLELISM})...",
            file=sys.stderr,
        )
        jd_cache = _fetch_jds_parallel(to_package)

    inbox_rows: list[InboxRow] = []
    cover_queue: list[dict] = []
    complete_count = 0
    incomplete_count = 0
    failed_count = 0

    for item in to_package:
        print(f"  - {item.title} @ {item.company}", file=sys.stderr)

        # Slug must match the on-disk dir name created by
        # workflow.create_application_package so INBOX links resolve.
        slug = company_dirname(item.company, item.job_id)

        if dry_run:
            print("    (dry run, skipping package creation)", file=sys.stderr)
            inbox_rows.append(
                InboxRow(
                    title=item.title,
                    company=item.company,
                    slug=slug,
                    score=item.score,
                    url=item.url,
                    status="[ ]",
                )
            )
            continue

        package_url = _resolve_apply_url(item)

        jd_text = jd_cache.get(item.url) if item.url else None
        if jd_text:
            body = jd_text
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False
            ) as f:
                f.write(f"# {item.title} @ {item.company}\n\n")
                f.write(f"Source: {item.url}\n")
                if package_url and package_url != item.url:
                    f.write(f"Direct apply: {package_url}\n")
                f.write("\n")
                f.write(body)
                jd_path = Path(f.name)
        else:
            body = (
                item.reason
                if hasattr(item, "reason")
                else "See listing URL for details."
            )
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(f"# {item.title} @ {item.company}\n\n")
                f.write(f"{body}\n\n")
                if item.url:
                    f.write(f"Source: {item.url}\n")
                if package_url and package_url != item.url:
                    f.write(f"Direct apply: {package_url}\n")
                jd_path = Path(f.name)

        eligible, location_reason = _location_eligibility(item, body)
        if not eligible:
            print(f"    ⏭️  Skipping: {location_reason}", file=sys.stderr)
            if jd_path and jd_path.exists():
                jd_path.unlink(missing_ok=True)
            continue

        try:
            # Create the application package
            workflow_result = create_application_package(
                WorkflowOptions(
                    project_root=root,
                    job_path=jd_path,
                    company=item.company,
                    position=item.title,
                    job_id=item.job_id,
                    source=item.source,
                    url=package_url or item.url,
                    priority="Medium",
                    dry_run=False,
                    render_pdf=True,
                )
            )

            # Report warnings
            for warning in workflow_result.warnings:
                print(f"    ⚠️ {warning}", file=sys.stderr)

            inbox_rows.append(
                InboxRow(
                    title=item.title,
                    company=item.company,
                    slug=slug,
                    score=item.score,
                    url=package_url or item.url,
                    status="[ ]",
                )
            )

            cover_warnings = [
                w for w in workflow_result.warnings if _is_cover_warning(w)
            ]
            if cover_warnings:
                incomplete_count += 1
                app_dir = workflow_result.application_dir
                cover_queue.append(
                    {
                        "company": item.company,
                        "position": item.title,
                        "cover_path": str(app_dir / "documents" / "cover-letter.md"),
                        "jd_path": str(app_dir / "research" / "job-description.md"),
                        "analysis_path": str(app_dir / "research" / "analysis.md"),
                        "resume_path": str(app_dir / "documents" / "resume.json"),
                        "warnings": cover_warnings,
                    }
                )
                print(
                    f"    ⚠️ INCOMPLETE — cover letter needs fill-in: {app_dir}",
                    file=sys.stderr,
                )
            else:
                complete_count += 1
                print(
                    f"    ✅ Package created at {workflow_result.application_dir}",
                    file=sys.stderr,
                )

        except Exception as e:
            failed_count += 1
            print(f"    ❌ Package creation failed: {e}", file=sys.stderr)
            # Still add to INBOX so user can see what failed
            inbox_rows.append(
                InboxRow(
                    title=item.title,
                    company=item.company,
                    slug=slug,
                    score=item.score,
                    url=package_url or item.url,
                    status="[ ]",
                )
            )
        finally:
            # Clean up temp JD file
            if jd_path and jd_path.exists():
                jd_path.unlink(missing_ok=True)

    print("\n📝 Phase 5: Writing INBOX.md...", file=sys.stderr)
    if dry_run:
        print(
            f"  Dry run: would write {len(inbox_rows)} rows to INBOX.md",
            file=sys.stderr,
        )
    else:
        write_inbox_rows(inbox, inbox_rows)
        print(f"  Wrote {len(inbox_rows)} rows to INBOX.md", file=sys.stderr)

    print(
        f"\n📊 Summary: {complete_count} complete, "
        f"{incomplete_count} incomplete (cover letter), "
        f"{failed_count} failed",
        file=sys.stderr,
    )

    if cover_queue:
        COVER_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(COVER_QUEUE_PATH, "w") as f:
            json.dump({"packages": cover_queue}, f, indent=2)
        print(
            f"\n⚠️ {incomplete_count} package(s) need cover letter fill-in.",
            file=sys.stderr,
        )
        print(f"   Queue written to: {COVER_QUEUE_PATH}", file=sys.stderr)
        print(
            "   Next: spawn an Agent subagent (Stage 4, no model override) "
            "to fill each cover letter from the queue. See the job-research skill.",
            file=sys.stderr,
        )
    else:
        print("\n✅ Pipeline complete — all cover letters filled.", file=sys.stderr)


def run_pipeline(
    root: Path,
    profiles: list[str] | None = None,
    score_cutoff: int | None = None,
    per_run_cap: int | None = None,
    sources: list[str] | None = None,
    dry_run: bool = False,
    fetch_jd: bool = True,
    reconcile_inbox: bool = True,
) -> None:
    """Default end-to-end flow: reconcile → scrape → score (in-process) → package."""
    profile_configs, sources, cutoff, cap = _resolve_config(
        profiles, sources, score_cutoff, per_run_cap
    )
    all_listings = do_reconcile_and_scrape(
        root, profile_configs, dry_run, reconcile_inbox=reconcile_inbox
    )
    if not all_listings:
        print("\n⚠️ No new listings found. Pipeline complete.", file=sys.stderr)
        return

    print("\n📊 Phase 3: Scoring listings...", file=sys.stderr)
    pre_filtered = [lst for lst in all_listings if not _snippet_location_excluded(lst)]
    dropped = len(all_listings) - len(pre_filtered)
    if dropped:
        print(
            f"  Pre-filter dropped {dropped} region-locked listings before scoring",
            file=sys.stderr,
        )
    scored = score_listings([vars(lst) for lst in pre_filtered])
    scored = sort_by_score(scored)
    passed = filter_by_score(scored, cutoff)
    print(f"  Above cutoff ({cutoff}): {len(passed)}", file=sys.stderr)

    do_package_from_scores(root, passed, cap, dry_run, fetch_jd, skip_reconcile=True)


def run_scrape_only(
    root: Path,
    outfile: Path,
    profiles: list[str] | None,
    sources: list[str] | None,
    dry_run: bool,
    reconcile_inbox: bool = True,
) -> None:
    """Run phases 1-2, dump listings + profile summary to JSON, exit.

    Output schema:
      {
        "profile_summary": "<text>",
        "cutoff": <int>,
        "cap": <int>,
        "listings": [
            {"job_id", "source", "title", "company", "url", "snippet", ...}
        ]
      }
    """
    profile_configs, _sources, cutoff, cap = _resolve_config(
        profiles, sources, None, None
    )
    all_listings = do_reconcile_and_scrape(
        root, profile_configs, dry_run, reconcile_inbox=reconcile_inbox
    )

    payload = {
        "profile_summary": candidate_summary(load_candidate_profile()),
        "cutoff": cutoff,
        "cap": cap,
        "listings": [vars(lst) for lst in all_listings],
    }
    outfile.parent.mkdir(parents=True, exist_ok=True)
    with open(outfile, "w") as f:
        json.dump(payload, f, indent=2)
    print(
        f"\n📤 Wrote {len(all_listings)} listings + profile summary to {outfile}",
        file=sys.stderr,
    )
    print(
        "   Next: have a Claude Code subagent score these and write back a",
        file=sys.stderr,
    )
    print("   scores file, then run:", file=sys.stderr)
    print("     python3 tools/pipeline.py --from-scores <scores.json>", file=sys.stderr)


def run_from_scores(
    root: Path,
    scores_file: Path,
    cap_override: int | None,
    dry_run: bool,
    fetch_jd: bool,
    reconcile_inbox: bool = True,
) -> None:
    """Run phases 4-5 from a pre-scored JSON file.

    Input schema (whichever the subagent emits):
      {
        "cap": <int>,                           # optional
        "scores": [
          {"job_id", "source", "title", "company", "url", "score", "reason"}, ...
        ]
      }
    Scores below cutoff should already be filtered out by the subagent.
    """
    with open(scores_file) as f:
        data = json.load(f)

    raw_scores = data.get("scores", [])
    passed = [
        ScoreResult(
            job_id=r["job_id"],
            source=r["source"],
            title=r.get("title", "Unknown"),
            company=r.get("company", "Unknown"),
            url=r.get("url"),
            score=int(r["score"]),
            reason=r.get("reason", ""),
        )
        for r in raw_scores
    ]
    passed = sort_by_score(passed)

    cap = cap_override or data.get("cap") or 10
    print(
        f"📥 Loaded {len(passed)} scored listings from {scores_file}", file=sys.stderr
    )
    do_package_from_scores(
        root, passed, cap, dry_run, fetch_jd, skip_reconcile=not reconcile_inbox
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the job research pipeline")
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        help="Search profile to run (can specify multiple times, default: all)",
    )
    parser.add_argument(
        "--cutoff",
        type=int,
        help="Score cutoff (default: from config or 65)",
    )
    parser.add_argument(
        "--cap",
        type=int,
        help="Per-run packager cap (default: from config or 10)",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Sources to scrape (can specify multiple times: linkedin, seek, hiringcafe, workingnomads, wellfound, weworkremotely)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-fetch-jd",
        action="store_true",
        help="Skip fetching full JD (use snippet only)",
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Skip the INBOX reconcile step in every mode "
        "(full pipeline Phase 1, --scrape-only Phase 1, and the pre-package "
        "reconcile inside --from-scores). Useful when re-running packaging "
        "without mutating INBOX/tracker.",
    )
    parser.add_argument(
        "--scrape-only",
        type=Path,
        metavar="OUTFILE",
        help="Run phases 1-2 only and dump listings + profile summary to OUTFILE (JSON). "
        "Use when an external scorer (e.g. Claude Code subagent) will score next.",
    )
    parser.add_argument(
        "--from-scores",
        type=Path,
        metavar="INFILE",
        help="Skip phases 1-3. Load scored listings from INFILE (JSON) and run "
        "phases 4-5 (package + write INBOX).",
    )
    args = parser.parse_args()

    if args.scrape_only and args.from_scores:
        parser.error("--scrape-only and --from-scores are mutually exclusive")

    root = project_root()

    if args.scrape_only:
        run_scrape_only(
            root=root,
            outfile=args.scrape_only,
            profiles=args.profiles,
            sources=args.sources,
            dry_run=args.dry_run,
            reconcile_inbox=not args.no_reconcile,
        )
        return

    if args.from_scores:
        run_from_scores(
            root=root,
            scores_file=args.from_scores,
            cap_override=args.cap,
            dry_run=args.dry_run,
            fetch_jd=not args.no_fetch_jd,
            reconcile_inbox=not args.no_reconcile,
        )
        return

    run_pipeline(
        root=root,
        profiles=args.profiles,
        score_cutoff=args.cutoff,
        per_run_cap=args.cap,
        sources=args.sources,
        dry_run=args.dry_run,
        fetch_jd=not args.no_fetch_jd,
        reconcile_inbox=not args.no_reconcile,
    )


if __name__ == "__main__":
    main()
