---
name: job-research
description: Run the automated job research pipeline. Scrapes LinkedIn and Seek for new listings, scores them against your resume via an Agent subagent, and generates tailored CV + cover letter packages for top matches. Use when the user says "job research", "find jobs", "scrape jobs", "run the pipeline", "start job search", or wants to see what's available.
compatibility: Requires file system access, Python 3, browser-harness for scraping (local Chrome), and typst for PDF rendering. Scoring uses a Claude Code subagent (no Anthropic API key required).
---

# Job Research Skill

Job discovery + package generation. The pipeline is split so the scoring step
runs as a Claude Code subagent instead of an inline LLM API call.

## Phases

1. **Reconcile + Scrape + Prep** (Python, `--scrape-only`) — archive
   submitted/skipped INBOX rows, scrape the sources, **dedup** against the
   tracker/INBOX, **fetch the full JD** for every survivor, then run the
   **location gate**. Dumps location-eligible listings (each carrying its
   `full_jd`) + candidate profile summary to a JSON file. All the cheap
   filtering happens here, before scoring, so the subagent only ever sees new,
   location-eligible jobs and packaging never re-fetches.
   Reconcile also handles **submit-time outreach**: for every row you marked
   `[x]` it runs Hunter contact discovery and, when a recipient is found,
   scaffolds a contact-aware `cold-email.md` in the archived package and lists
   it in `/tmp/jobhunting-coldmail-queue.json` for the fill step below.
2. **Score** (Agent subagent) — reads the listings file and
   `tools/scoring-rubric.md`, scores each **full JD**, emits a filtered scores
   file.
3. **Package** (Python, `--from-scores --listings`) — joins scores to the
   listings dump by `job_id` to reuse the fetched JDs, builds tailored CV +
   cover-letter **scaffold** for the capped top matches, appends rows to
   `applications/INBOX.md`. Emits a `/tmp/jobhunting-cover-queue.json` file
   listing any packages whose cover letter still has unresolved placeholders.
4. **Fill Cover Letters** (Agent subagent) — reads the queue file and writes
   a tailored body into each scaffold cover-letter.md. Required: Phase 3 only
   scaffolds; it does _not_ call an LLM.
5. **Render Cover PDFs** (Python/Typst) — after placeholders are removed,
   render each `cover-letter.md` to sibling `cover-letter.pdf`.
6. **Fill Cold Emails** (Agent subagent) — only when Phase 1's reconcile queued
   any. Reads `/tmp/jobhunting-coldmail-queue.json` and writes a full,
   role-aware body into each scaffold tied to the discovered recipient. The
   cold email is only generated once you commit (marked `[x]`) and Hunter has
   resolved who to address — never at package time.
7. **One-off Outreach Prep** (Python + per-company subagent) — for already
   submitted jobs, prepare a selected set of archived packages into a queue and
   run one subagent per company. Each subagent may inspect existing
   `contacts.json`, validate the current contact choice, try additional
   evidence-based digging, and only then write `cold-email.md`.

## How to run (orchestrated by Claude Code)

```bash
# Stage 1: reconcile + scrape + dedup + fetch full JD + location gate
python3 tools/pipeline.py --scrape-only /tmp/jobhunting-listings.json
```

**If Stage 1 outputs 0 listings, stop here.** There is nothing to score or
package. Report the result and wait for the user's next instruction.

If Stage 1 prints `✉️ N cold email(s) need body fill-in`, those are outreach
emails for jobs you marked `[x]`. Spawn a cold-email fill subagent (a light /
cost-efficient model is fine). This is independent of scoring/packaging — run
it whenever after Stage 1.

> Read `/tmp/jobhunting-coldmail-queue.json`. For each entry, read its
> `cold_email_path` (scaffold), `contacts_path`, `jd_path`, `analysis_path`,
> and `resume_path`, plus `LinkedIn-CV-Profile.md` for the candidate's truthful
> background. Rewrite `cold_email_path` with a tight, **role-aware** body
> following `templates/cold-email.md`'s authoring rules: tailor the pitch to
> the recipient named in `contacts_path` — recruiter/talent → fit + logistics;
> hiring manager / eng leader / CTO → technical depth. Never invent experience.
> Replace **every** `[bracketed placeholder]`. Keep the existing subject,
> salutation (already filled with the contact's first name), and signoff;
> remove the auto-generated context HTML comment before finishing. Report
> per-company recipient + role and any emails you flagged as risky.

For one-off outreach prep on already-submitted jobs:

```bash
# List submitted applications with stable 1-based numbers
python3 tools/outreach.py list-submitted

# Prepare a queue for selected submitted applications
python3 tools/outreach.py prepare --pick 3 16 --output /tmp/jobhunting-outreach-queue.json

# Prepare a queue for automatic per-company subagent launch
python3 tools/outreach.py run --pick 3 16 --output /tmp/jobhunting-outreach-queue.json
```

`tools/outreach.py run` writes queue entries that already include the custom
subagent type (`outreach-company`) plus a per-company prompt. The orchestrator
should read `/tmp/jobhunting-outreach-queue.json` and launch **one background
subagent per target** using each entry's `subagent_type`, `agent_description`,
and `agent_prompt`.

Suggested subagent prompt skeleton:

> Read this outreach target's `contacts_path`, `jd_path`, `analysis_path`,
> `resume_path`, `cold_email_path`, and `LinkedIn-CV-Profile.md`. This is for
> one already-submitted application package. First evaluate whether the current
> contacts are usable. If they are weak or empty, try additional evidence-based
> contact discovery using available tools, but never invent a contact. Choose
> the best recipient, flag any wrong-entity / wrong-region / low-confidence
> risks, and only if the contact is good enough rewrite `cold_email_path` into
> a complete, role-aware email. Replace all placeholders and remove the
> auto-generated context HTML comment before finishing. Report status
> (`ready|risky_contact|no_contact_found`), chosen recipient, evidence, and
> whether the file was updated.

Then spawn a scoring subagent using this prompt skeleton. Use a **light /
cost-efficient model** — this scores ~50-80 full JDs per run, and scoring is
judgment but not deep reasoning, so a light model is the right tradeoff; avoid
heavyweight reasoning models here. Let the orchestrator choose the appropriate
light-tier model for the current tool/runtime.

> Read `/tmp/jobhunting-listings.json` and apply the rubric at
> `tools/scoring-rubric.md`. Each listing carries a `full_jd` field — score
> against the **full JD**, not just the title/snippet. Write filtered + sorted
> scores to `/tmp/jobhunting-scores.json` per the schema documented in the
> rubric. Report kept-vs-input count, top 5 titles + scores, and any patterns
> in what was dropped.

If scoring keeps zero listings, skip Stage 3 and report zero packages.

```bash
# Stage 3: package (cap 100 = process every listing that passed cutoff)
# --listings reuses the full JDs fetched in Stage 1 (no re-fetch).
python3 tools/pipeline.py --from-scores /tmp/jobhunting-scores.json \
  --listings /tmp/jobhunting-listings.json --cap 100
```

If Stage 3 prints `⚠️ N package(s) need cover letter fill-in`, run Stage 4:
spawn another subagent using this prompt skeleton. A light / cost-efficient
model is fine here too.

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

## Why a subagent

- **Subagent over SDK call**: keeps scoring in the agent session,
  no API-key plumbing, easier to iterate on the rubric.
- **Light model, set by the orchestrator**: prefer a cost-efficient model for
  scoring and cover-letter fill — judgment-capable, cheap. Do not hardcode a
  model name in this skill; let the orchestrator pick the right light-tier
  model for the current tool/runtime.

## Other flags

Scoring is pure-LLM via the subagent — there is no single-command path. Flags
apply to the `--scrape-only` (Stage 1) and `--from-scores` (Stage 3) invocations.

```bash
python3 tools/pipeline.py --scrape-only OUT --profile product-engineer --profile ai-native
python3 tools/pipeline.py --scrape-only OUT --source linkedin --source workingnomads
python3 tools/pipeline.py --scrape-only OUT --dry-run   # reconcile/scrape, skip JD fetch
python3 tools/pipeline.py --from-scores SCORES --listings OUT --cap 5   # limit packages
```

The score cutoff lives in `tools/scoring-rubric.md` (the subagent applies it);
`--cutoff` is no longer a pipeline flag.

## Search profiles

Edit `tools/search-config.json`: keywords + default sources/cutoff/cap.
Current profiles: `product-engineer`, `ai-native`.

## Workflow

1. Run Stage 1. If 0 listings came through, stop and report — no further stages needed. Otherwise continue with scoring subagent → Stage 3 → cover-letter fill → PDF render.
2. Review `INBOX.md` — check off `[x]` what you submit, mark `[~]` to skip.
3. Next run auto-archives checked / skipped items and fetches fresh listings.

## Notes

- Jobs are deduped against `application-tracker.json` `seen_jobs`.
- Skipped jobs (`[~]`) go into `skipped_jobs` and are never re-suggested.
- Browser-harness auto-starts on first scrape call.
- Hiring.cafe and Working Nomads must be scraped with targeted JavaScript selectors only; never use full-page text extraction on listing/search pages because it can blow out context. Extract structured card data (title/company/location/snippet/job URL) from visible cards, and if selectors fail, inspect a screenshot/DOM and update the targeted selector. Keep globally/fully remote roles and Auckland/NZ/AU/APAC-friendly roles; skip roles explicitly location-limited outside those regions. These boards are discovery sources; prefer resolving direct employer/apply URLs for final review when available.
- Scoring rubric lives at `tools/scoring-rubric.md`. Edit there, not in prompts.
