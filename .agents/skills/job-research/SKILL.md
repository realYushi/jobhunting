---
name: job-research
description: Run the automated job research pipeline. Scrapes LinkedIn and Seek for new listings, scores them against your resume via a Sonnet subagent, and generates tailored CV + cover letter packages for top matches. Use when the user says "job research", "find jobs", "scrape jobs", "run the pipeline", "start job search", or wants to see what's available.
compatibility: Requires file system access, Python 3, browser-harness for scraping (local Chrome, CloakBrowser, Browserless, or Lightpanda), and typst for PDF rendering. Scoring uses a Claude Code subagent (no Anthropic API key required).
---

# Job Research Skill

Job discovery + package generation. The pipeline is split so the scoring step
runs as a Claude Code subagent (Sonnet) instead of an inline LLM API call.

## Phases

1. **Reconcile + Scrape** (Python) — archive submitted/skipped INBOX rows, then
   scrape LinkedIn + Seek + Hiring.cafe. Dumps listings to a JSON file.
2. **Score** (Sonnet subagent) — reads the listings file and
   `tools/scoring-rubric.md`, emits a filtered scores file.
3. **Package** (Python) — fetches full JDs, builds tailored CV + cover-letter
   **scaffold**, appends rows to `applications/INBOX.md`. Emits a
   `/tmp/jobhunting-cover-queue.json` file listing any packages whose cover
   letter still has unresolved placeholders.
4. **Fill Cover Letters** (Sonnet subagent) — reads the queue file and writes
   a tailored body into each scaffold cover-letter.md. Required: Phase 3 only
   scaffolds; it does _not_ call an LLM.
5. **Render Cover PDFs** (Python/Typst) — after placeholders are removed,
   render each `cover-letter.md` to sibling `cover-letter.pdf`.

## How to run (orchestrated by Claude Code)

```bash
# Stage 1: scrape
python3 tools/pipeline.py --scrape-only /tmp/jobhunting-listings.json
```

Then spawn an Agent subagent with **`model: "sonnet"`** using this prompt
skeleton:

> Read `/tmp/jobhunting-listings.json` and apply the rubric at
> `tools/scoring-rubric.md`. Write filtered + sorted scores to
> `/tmp/jobhunting-scores.json` per the schema documented in the rubric.
> Report kept-vs-input count, top 5 titles + scores, and any patterns in
> what was dropped.

```bash
# Stage 3: package (cap 100 = process every listing that passed cutoff)
python3 tools/pipeline.py --from-scores /tmp/jobhunting-scores.json --cap 100
```

If Stage 3 prints `⚠️ N package(s) need cover letter fill-in`, run Stage 4:
spawn another Sonnet subagent using this prompt skeleton:

> Read `/tmp/jobhunting-cover-queue.json`. For each entry, read its
> `cover_path` (scaffold), `jd_path`, `analysis_path`, and `resume_path`,
> plus `templates/base-resume.json` and `LinkedIn-CV-Profile.md` for the
> candidate's truthful background. Rewrite `cover_path` with a tailored
> 3-paragraph, 200-400 word letter following `templates/cover-letter.md`'s
> authoring rules and `templates/quality-framework.md`. Never invent
> experience. Replace **every** `[bracketed placeholder]`. Preserve the
> existing salutation, signoff, and any auto-generated context HTML
> comments at the end. Report: per-company word count and any letters
> you flagged as risky.

Then render the filled letters to PDF:

```bash
python3 tools/cover_letter_pdf.py --queue /tmp/jobhunting-cover-queue.json --force
```

For one-off rendering:

```bash
python3 tools/cover_letter_pdf.py --file "applications/active/Company/documents/cover-letter.md" --force
```

## Why Sonnet, why a subagent

- **Sonnet over Haiku**: scoring needs domain judgment ("is this company /
  vertical on track?") that Haiku has been unreliable on — it kept
  defence/aerospace, data eng, and ERP integration roles past the cutoff.
- **Subagent over SDK call**: keeps scoring inside the Claude Code session,
  no API-key plumbing, easier to iterate on the rubric.
- **Single pass over two-pass**: a tight rubric with Sonnet matches a
  Haiku + Sonnet two-pass at roughly half the cost.

## Single-command fallback

```bash
python3 tools/pipeline.py
```

Runs scrape + in-process keyword scoring + package. The keyword fallback
(`tools/lib/scorer.py`) is fine as a sanity net but won't catch domain /
company off-track signals. Prefer the orchestrated flow above.

## Other flags

```bash
python3 tools/pipeline.py --profile fullstack --profile ai-engineer
python3 tools/pipeline.py --cutoff 70    # raise score threshold (default: 65)
python3 tools/pipeline.py --cap 5        # limit packages per run
python3 tools/pipeline.py --source linkedin
python3 tools/pipeline.py --source workingnomads
python3 tools/pipeline.py --no-fetch-jd  # use snippet only, skip JD scrape
python3 tools/pipeline.py --dry-run
```

## Search profiles

Edit `tools/search-config.json`: keywords, location, remote, experience_level.
Current profiles: `fullstack`, `frontend`, `backend`, `ai-engineer`.

## Workflow

1. Run the orchestrated 3-stage flow (or `pipeline.py` for the quick path).
2. Review `INBOX.md` — check off `[x]` what you submit, mark `[~]` to skip.
3. Next run auto-archives checked / skipped items and fetches fresh listings.

## Notes

- Jobs are deduped against `application-tracker.json` `seen_jobs`.
- Skipped jobs (`[~]`) go into `skipped_jobs` and are never re-suggested.
- Browser-harness auto-starts on first scrape call.
- To run all browser automation through Browserless on a VPS, start Browserless
  (`python3 tools/start_browserless.py --pull` for self-hosted Docker, or use a
  hosted Browserless WebSocket URL), then export
  `JOBHUNTING_BROWSER=browserless` and `JOBHUNTING_BROWSERLESS_CDP_WS=...`
  before running the pipeline. This routes LinkedIn public jobs, Seek,
  Hiring.cafe, Wellfound, WWR, and full-JD fetches through the same remote
  Chromium backend.
- Hiring.cafe and Working Nomads must be scraped with targeted JavaScript selectors only; never use full-page text extraction on listing/search pages because it can blow out context. Extract structured card data (title/company/location/snippet/job URL) from visible cards, and if selectors fail, inspect a screenshot/DOM and update the targeted selector. Keep globally/fully remote roles and Auckland/NZ/AU/APAC-friendly roles; skip roles explicitly location-limited outside those regions. These boards are discovery sources; prefer resolving direct employer/apply URLs for final review when available.
- Scoring rubric lives at `tools/scoring-rubric.md`. Edit there, not in prompts.
