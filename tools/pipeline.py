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
from pathlib import Path

from lib.harness_utils import load_script, run_harness
from lib.inbox import InboxRow, write_inbox_rows
from lib.paths import company_dirname, inbox_path as default_inbox, project_root
from lib.reconcile import reconcile
from lib.tracker import load_tracker
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

    Uses browser-harness to navigate and extract the JD text.
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

    # Parse JSON output
    from lib.harness_utils import parse_harness_json_output

    results = parse_harness_json_output(stdout)
    if results and "jd" in results[0]:
        return results[0]["jd"]

    return f"# Could not extract JD from {url}"


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
) -> list[JobListing]:
    """Phases 1-2: reconcile INBOX, then scrape sources."""
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
    """Normalize company/title text for cross-id duplicate detection."""
    return " ".join((value or "").casefold().split())


def _existing_company_title_matches(root: Path, item: ScoreResult) -> list[dict]:
    """Return existing applications with the same company and title.

    This catches job boards re-listing the same role under a new id, where the
    exact (source, job_id) dedupe cannot help.
    """
    tracker = load_tracker(root / "applications" / "application-tracker.json")
    company = _norm_identity_text(item.company)
    title = _norm_identity_text(item.title)
    matches: list[dict] = []
    for bucket_items in tracker.get("applications", {}).values():
        for app in bucket_items:
            if (
                _norm_identity_text(app.get("company")) == company
                and _norm_identity_text(app.get("position")) == title
                and str(app.get("job_id", "")) != str(item.job_id)
            ):
                matches.append(app)
    return matches


def _is_cover_warning(warning: str) -> bool:
    """A warning is cover-letter related if it mentions placeholders or 'Cover letter'."""
    return "placeholder" in warning.lower() or "cover letter" in warning.lower()


def do_package_from_scores(
    root: Path,
    passed: list[ScoreResult],
    cap: int,
    dry_run: bool,
    fetch_jd: bool,
) -> None:
    """Phases 4-5: build packages and write INBOX."""
    inbox = default_inbox(root)
    print("\n📦 Phase 4: Creating application packages...", file=sys.stderr)
    to_package: list[ScoreResult] = []
    for item in passed:
        matches = _existing_company_title_matches(root, item)
        if matches:
            match = matches[0]
            print(
                "  ⏭️  Skipping duplicate company/title: "
                f"{item.title} @ {item.company} "
                f"(existing {match.get('status', 'Unknown')} "
                f"job_id={match.get('job_id', 'manual')})",
                file=sys.stderr,
            )
            continue
        to_package.append(item)
        if len(to_package) >= cap:
            break
    print(f"  Creating {len(to_package)} packages (cap: {cap})", file=sys.stderr)

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

        # Fetch full JD if URL available
        jd_path: Path | None = None
        if fetch_jd and item.url:
            try:
                jd_text = _fetch_full_jd(item.url)
                # Write to a temp file for the workflow
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False
                ) as f:
                    f.write(f"# {item.title} @ {item.company}\n\n")
                    f.write(f"Source: {item.url}\n")
                    if package_url and package_url != item.url:
                        f.write(f"Direct apply: {package_url}\n")
                    f.write("\n")
                    f.write(jd_text)
                    jd_path = Path(f.name)
            except Exception as e:
                print(f"    Failed to fetch JD: {e}", file=sys.stderr)

        if jd_path is None:
            # Create a minimal JD from the snippet
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(f"# {item.title} @ {item.company}\n\n")
                snippet = (
                    item.reason
                    if hasattr(item, "reason")
                    else "See listing URL for details."
                )
                f.write(f"{snippet}\n\n")
                if item.url:
                    f.write(f"Source: {item.url}\n")
                if package_url and package_url != item.url:
                    f.write(f"Direct apply: {package_url}\n")
                jd_path = Path(f.name)

        eligible, location_reason = _location_eligibility(item, jd_path.read_text())
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
            "   Next: spawn a Sonnet subagent (Stage 4) to fill each "
            "cover letter from the queue. See the job-research skill.",
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
) -> None:
    """Default end-to-end flow: reconcile → scrape → score (in-process) → package."""
    profile_configs, sources, cutoff, cap = _resolve_config(
        profiles, sources, score_cutoff, per_run_cap
    )
    all_listings = do_reconcile_and_scrape(root, profile_configs, dry_run)
    if not all_listings:
        print("\n⚠️ No new listings found. Pipeline complete.", file=sys.stderr)
        return

    print("\n📊 Phase 3: Scoring listings...", file=sys.stderr)
    scored = score_listings([vars(lst) for lst in all_listings])
    scored = sort_by_score(scored)
    passed = filter_by_score(scored, cutoff)
    print(f"  Above cutoff ({cutoff}): {len(passed)}", file=sys.stderr)

    do_package_from_scores(root, passed, cap, dry_run, fetch_jd)


def run_scrape_only(
    root: Path,
    outfile: Path,
    profiles: list[str] | None,
    sources: list[str] | None,
    dry_run: bool,
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
    all_listings = do_reconcile_and_scrape(root, profile_configs, dry_run)

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
    do_package_from_scores(root, passed, cap, dry_run, fetch_jd)


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
        )
        return

    if args.from_scores:
        run_from_scores(
            root=root,
            scores_file=args.from_scores,
            cap_override=args.cap,
            dry_run=args.dry_run,
            fetch_jd=not args.no_fetch_jd,
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
    )


if __name__ == "__main__":
    main()
