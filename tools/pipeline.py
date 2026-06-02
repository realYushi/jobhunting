"""Job research pipeline orchestrator.

Runs as two orchestrated stages around a Claude Code scoring subagent (there is
no single-command path; scoring is pure-LLM, not deterministic):

  1. --scrape-only OUT   Phases 1-5: reconcile INBOX → scrape sources → dedup vs
                         tracker/INBOX → fetch full JD for all survivors →
                         location gate. Dumps eligible listings (with full_jd)
                         + candidate profile summary to OUT.
  2. <scoring subagent>  Phase 6: scores the full JDs against
                         tools/scoring-rubric.md, writes a filtered scores file.
  3. --from-scores IN    Phases 7-8: package CV + cover letter for the capped
                         top matches (reusing full JDs via --listings) and
                         append rows to INBOX.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from lib.dedup import (
    _build_application_key_index,
    _build_company_title_index,
    _build_inbox_indexes,
    _duplicate_reason,
)
from lib.filters import (
    _company_hard_drop_reason,
    _location_eligibility,
    _snippet_location_excluded,
    _title_hard_drop_reason,
)
from lib.inbox import InboxRow, write_inbox_rows
from lib.jd_fetch import JD_FETCH_PARALLELISM, _fetch_jds_parallel
from lib.paths import company_dirname, inbox_path as default_inbox, project_root
from lib.reconcile import ReconcileResult, parse_inbox, reconcile
from lib.tracker import load_keyset, load_tracker
from lib.scorer import (
    ScoreResult,
    candidate_summary,
    load_candidate_profile,
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
    """Phases 1-2: reconcile INBOX, sync LinkedIn statuses, then scrape."""
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
        _write_coldmail_queue(result)
    else:
        print("🔄 Phase 1: Skipping INBOX reconcile (--no-reconcile)", file=sys.stderr)

    print("\n🔍 Phase 2: Scraping job listings...", file=sys.stderr)
    all_listings: list[JobListing] = []
    scrape_summary: ScrapeSummary | None = None
    try:
        all_listings, scrape_summary = smart_scrape(
            profiles=profile_configs,
            max_total=100,
        )
        if scrape_summary:
            print_summary(scrape_summary)
    except Exception as e:
        print(f"  Scraping failed: {e}", file=sys.stderr)
        print("  Continuing with empty listing set...", file=sys.stderr)

    print(f"  Total listings to score: {len(all_listings)}", file=sys.stderr)
    return all_listings


COVER_QUEUE_PATH = Path("/tmp/jobhunting-cover-queue.json")
COLDMAIL_QUEUE_PATH = Path("/tmp/jobhunting-coldmail-queue.json")


def _write_coldmail_queue(result: ReconcileResult) -> None:
    """Persist submit-time cold-email scaffolds for the body-fill subagent.

    reconcile() scaffolds a contact-aware cold-email for each [x] submission
    that resolved a recipient; the orchestrator fills the body on this run.
    """
    queue = result.coldmail_queue
    if not queue:
        return
    COLDMAIL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COLDMAIL_QUEUE_PATH, "w") as f:
        json.dump({"emails": queue}, f, indent=2)
    print(f"\n✉️  {len(queue)} cold email(s) need body fill-in.", file=sys.stderr)
    print(f"   Queue written to: {COLDMAIL_QUEUE_PATH}", file=sys.stderr)


def _is_cover_warning(warning: str) -> bool:
    """A warning is cover-letter related if it mentions placeholders or 'Cover letter'."""
    return "placeholder" in warning.lower() or "cover letter" in warning.lower()


def do_package_from_scores(
    root: Path,
    passed: list[ScoreResult],
    cap: int,
    dry_run: bool,
    listings_by_id: dict[str, dict] | None = None,
    skip_reconcile: bool = False,
) -> None:
    """Phases 7-8: build packages and write INBOX.

    Full JD text, the dedup pass, and the location gate all happen upstream in
    ``run_scrape_only`` now. ``listings_by_id`` carries each scored listing's
    pre-fetched ``full_jd`` (keyed by ``job_id``) so packaging never re-fetches.
    The dedup loop below is kept as a cheap, fetch-free final guard against rows
    submitted/skipped between the scrape and package stages.
    """
    listings_by_id = listings_by_id or {}
    inbox = default_inbox(root)
    print("\n📦 Phase 7: Creating application packages...", file=sys.stderr)

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
        _write_coldmail_queue(reconcile_result)

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

        jd_text = (listings_by_id.get(item.job_id) or {}).get("full_jd") or None
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


def _dedup_survivors(
    root: Path, inbox: Path, listings: list[JobListing]
) -> list[JobListing]:
    """Phase 3: drop listings already applied/skipped/in INBOX (fetch-free).

    Runs before the expensive JD fetch + scoring so we never pay to fetch or
    score a job we've already handled. Reuses the same ``_duplicate_reason``
    indexes the packaging guard uses; ``JobListing`` exposes the same
    ``source``/``job_id``/``company``/``title``/``url`` attributes the dedup
    helpers read off a ``ScoreResult``.
    """
    tracker = load_tracker(root / "applications" / "application-tracker.json")
    skipped_set = load_keyset(tracker, "skipped")
    application_key_index = _build_application_key_index(tracker)
    company_title_index = _build_company_title_index(tracker)
    inbox_key_index, inbox_company_title_index = _build_inbox_indexes(parse_inbox(inbox))

    survivors: list[JobListing] = []
    for lst in listings:
        reason = _duplicate_reason(
            lst,
            application_key_index=application_key_index,
            company_title_index=company_title_index,
            inbox_key_index=inbox_key_index,
            inbox_company_title_index=inbox_company_title_index,
            skipped_set=skipped_set,
        )
        if reason:
            print(
                f"  ⏭️  Dedup: {lst.title} @ {lst.company} ({reason})",
                file=sys.stderr,
            )
            continue
        survivors.append(lst)
    return survivors


def run_scrape_only(
    root: Path,
    outfile: Path,
    profiles: list[str] | None,
    sources: list[str] | None,
    dry_run: bool,
    reconcile_inbox: bool = True,
) -> None:
    """Phases 1-5: reconcile → scrape → dedup → fetch full JD → location gate.

    Dumps location-eligible, deduped listings (each carrying its pre-fetched
    ``full_jd``) plus the candidate profile summary to OUTFILE for the scoring
    subagent. Because JD text is fetched here once, ``--from-scores`` packaging
    never re-fetches.

    Output schema:
      {
        "profile_summary": "<text>",
        "cutoff": <int>,
        "cap": <int>,
        "listings": [
            {"job_id","source","title","company","url","location","snippet","full_jd"}
        ]
      }
    """
    profile_configs, _sources, cutoff, cap = _resolve_config(
        profiles, sources, None, None
    )
    inbox = default_inbox(root)
    all_listings = do_reconcile_and_scrape(
        root, profile_configs, dry_run, reconcile_inbox=reconcile_inbox
    )

    print("\n🧹 Phase 3: Deduping against tracker / INBOX...", file=sys.stderr)
    survivors = _dedup_survivors(root, inbox, all_listings)
    print(f"  After dedup: {len(survivors)} new listings", file=sys.stderr)

    # Cheap pre-fetch trim: drop obvious title hard-drops and hard
    # region-locked snippets before paying to fetch the full JD.
    pre_trimmed: list[JobListing] = []
    dropped_title = 0
    dropped_region = 0
    dropped_company = 0
    for lst in survivors:
        title_reason = _title_hard_drop_reason(lst)
        if title_reason:
            dropped_title += 1
            print(
                f"  ⏭️  Pre-fetch title trim: {lst.title} @ {lst.company} ({title_reason})",
                file=sys.stderr,
            )
            continue
        company_reason = _company_hard_drop_reason(lst)
        if company_reason:
            dropped_company += 1
            print(
                f"  ⏭️  Pre-fetch company trim: {lst.title} @ {lst.company} ({company_reason})",
                file=sys.stderr,
            )
            continue
        if _snippet_location_excluded(lst):
            dropped_region += 1
            continue
        pre_trimmed.append(lst)
    if dropped_title:
        print(
            f"  Pre-fetch title trim dropped {dropped_title} listings",
            file=sys.stderr,
        )
    if dropped_company:
        print(
            f"  Pre-fetch company trim dropped {dropped_company} listings",
            file=sys.stderr,
        )
    if dropped_region:
        print(
            f"  Pre-fetch trim dropped {dropped_region} region-locked listings",
            file=sys.stderr,
        )

    jd_cache: dict[str, str] = {}
    if not dry_run and pre_trimmed:
        print(
            f"\n📄 Phase 4: Fetching {len(pre_trimmed)} full JDs in parallel "
            f"(workers={JD_FETCH_PARALLELISM})...",
            file=sys.stderr,
        )
        jd_cache = _fetch_jds_parallel(pre_trimmed)

    print("\n🌏 Phase 5: Location gate on full JD...", file=sys.stderr)
    listings_out: list[dict] = []
    dropped_loc = 0
    for lst in pre_trimmed:
        jd_text = jd_cache.get(lst.url, "") if lst.url else ""
        if not dry_run:
            eligible, location_reason = _location_eligibility(lst, jd_text)
            if not eligible:
                dropped_loc += 1
                print(
                    f"  ⏭️  Location gate: {lst.title} @ {lst.company} "
                    f"({location_reason})",
                    file=sys.stderr,
                )
                continue
        listings_out.append(
            {
                "job_id": lst.job_id,
                "source": lst.source,
                "title": lst.title,
                "company": lst.company,
                "url": lst.url,
                "location": lst.location,
                "snippet": lst.snippet,
                "full_jd": jd_text,
            }
        )
    if dropped_loc:
        print(f"  Location gate dropped {dropped_loc} listings", file=sys.stderr)

    payload = {
        "profile_summary": candidate_summary(load_candidate_profile()),
        "cutoff": cutoff,
        "cap": cap,
        "listings": listings_out,
    }
    outfile.parent.mkdir(parents=True, exist_ok=True)
    with open(outfile, "w") as f:
        json.dump(payload, f, indent=2)
    print(
        f"\n📤 Wrote {len(listings_out)} listings + profile summary to {outfile}",
        file=sys.stderr,
    )
    print(
        "   Next: have a Claude Code subagent score these (full JD) per",
        file=sys.stderr,
    )
    print("   tools/scoring-rubric.md, then run:", file=sys.stderr)
    print(
        "     python3 tools/pipeline.py --from-scores <scores.json> "
        f"--listings {outfile}",
        file=sys.stderr,
    )


def run_from_scores(
    root: Path,
    scores_file: Path,
    listings_file: Path | None,
    cap_override: int | None,
    dry_run: bool,
    reconcile_inbox: bool = True,
) -> None:
    """Phases 7-8: package + write INBOX from a pre-scored JSON file.

    Input schema (emitted by the scoring subagent):
      {
        "cap": <int>,                           # optional
        "scores": [
          {"job_id", "source", "title", "company", "url", "score", "reason"}, ...
        ]
      }
    Scores below cutoff should already be filtered out by the subagent.

    ``listings_file`` is the ``--scrape-only`` dump; its embedded ``full_jd`` is
    joined onto each score by ``job_id`` so packaging uses the JD fetched
    upstream rather than re-fetching. Title/company/url missing from a score are
    backfilled from the joined listing.
    """
    with open(scores_file) as f:
        data = json.load(f)

    listings_by_id: dict[str, dict] = {}
    if listings_file:
        with open(listings_file) as f:
            listings_data = json.load(f)
        for lst in listings_data.get("listings", []):
            jid = lst.get("job_id")
            if jid:
                listings_by_id[jid] = lst

    raw_scores = data.get("scores", [])
    passed = []
    for r in raw_scores:
        lst = listings_by_id.get(r["job_id"], {})
        # source/title/company/url all backfill from the joined listing so a
        # scoring subagent that emits a minimal record (just job_id+score+reason)
        # doesn't crash packaging after scraping/scoring budget is already spent.
        passed.append(
            ScoreResult(
                job_id=r["job_id"],
                source=r.get("source") or lst.get("source") or "",
                title=r.get("title") or lst.get("title", "Unknown"),
                company=r.get("company") or lst.get("company", "Unknown"),
                url=r.get("url") or lst.get("url"),
                score=int(r["score"]),
                reason=r.get("reason", ""),
            )
        )
    passed = sort_by_score(passed)

    cap = cap_override or data.get("cap") or 10
    print(
        f"📥 Loaded {len(passed)} scored listings from {scores_file}", file=sys.stderr
    )
    if listings_file:
        print(
            f"   Joined {len(listings_by_id)} full JDs from {listings_file}",
            file=sys.stderr,
        )
    elif passed and not dry_run:
        # Without --listings, JDs haven't been pre-fetched and the location
        # gate hasn't run. Fetch + gate inline so packaging matches the
        # --scrape-only path; otherwise we'd tailor against the scorer's
        # one-line reason and ship region-locked roles.
        print(
            f"\n📄 Fetching {len(passed)} full JDs in parallel "
            f"(no --listings, workers={JD_FETCH_PARALLELISM})...",
            file=sys.stderr,
        )
        jd_cache = _fetch_jds_parallel(passed)
        print("\n🌏 Location gate on full JD...", file=sys.stderr)
        filtered: list[ScoreResult] = []
        dropped_loc = 0
        for item in passed:
            jd_text = jd_cache.get(item.url, "") if item.url else ""
            eligible, location_reason = _location_eligibility(item, jd_text)
            if not eligible:
                dropped_loc += 1
                print(
                    f"  ⏭️  Location gate: {item.title} @ {item.company} "
                    f"({location_reason})",
                    file=sys.stderr,
                )
                continue
            if item.job_id:
                listings_by_id[item.job_id] = {"full_jd": jd_text}
            filtered.append(item)
        if dropped_loc:
            print(f"  Location gate dropped {dropped_loc} listings", file=sys.stderr)
        passed = filtered
    do_package_from_scores(
        root,
        passed,
        cap,
        dry_run,
        listings_by_id=listings_by_id,
        skip_reconcile=not reconcile_inbox,
    )


def main() -> None:
    # Scrape through the user's own logged-in Chrome by default so runs reuse
    # existing cookies (wellfound login, We Work Remotely's Cloudflare
    # clearance) instead of hitting login/bot walls in a clean profile. Set
    # JOBHUNTING_BROWSER_USE_DEDICATED=1 to scrape in an isolated background
    # Chrome instead (no cookies, but it won't touch the user's tabs).
    os.environ.setdefault("JOBHUNTING_BROWSER_USE_DEDICATED", "0")

    parser = argparse.ArgumentParser(description="Run the job research pipeline")
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        help="Search profile to run (can specify multiple times, default: all)",
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
        help="Sources to scrape (can specify multiple times: linkedin, seek, hiringcafe, workingnomads, wellfound, weworkremotely, prosple)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Skip the INBOX reconcile step (--scrape-only Phase 1 and the "
        "pre-package reconcile inside --from-scores). Useful when re-running "
        "packaging without mutating INBOX/tracker.",
    )
    parser.add_argument(
        "--scrape-only",
        type=Path,
        metavar="OUTFILE",
        help="Run phases 1-5 (reconcile, scrape, dedup, fetch full JD, location "
        "gate) and dump location-eligible listings (with full_jd) + profile "
        "summary to OUTFILE (JSON), for the scoring subagent to score next.",
    )
    parser.add_argument(
        "--from-scores",
        type=Path,
        metavar="INFILE",
        help="Skip phases 1-6. Load scored listings from INFILE (JSON) and run "
        "phases 7-8 (package + write INBOX). Pair with --listings to reuse the "
        "full JDs fetched during --scrape-only.",
    )
    parser.add_argument(
        "--listings",
        type=Path,
        metavar="LISTINGS",
        help="The --scrape-only dump; joined onto --from-scores by job_id so "
        "packaging reuses the upstream full JDs instead of re-fetching.",
    )
    args = parser.parse_args()

    if args.scrape_only and args.from_scores:
        parser.error("--scrape-only and --from-scores are mutually exclusive")
    if args.listings and not args.from_scores:
        parser.error("--listings is only valid together with --from-scores")

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
            listings_file=args.listings,
            cap_override=args.cap,
            dry_run=args.dry_run,
            reconcile_inbox=not args.no_reconcile,
        )
        return

    parser.error(
        "no mode selected. The pipeline runs as two orchestrated stages:\n"
        "  1. python3 tools/pipeline.py --scrape-only /tmp/jobhunting-listings.json\n"
        "  2. <scoring subagent scores per tools/scoring-rubric.md>\n"
        "  3. python3 tools/pipeline.py --from-scores /tmp/jobhunting-scores.json "
        "--listings /tmp/jobhunting-listings.json\n"
        "See the job-research skill."
    )


if __name__ == "__main__":
    main()
