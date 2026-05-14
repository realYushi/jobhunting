# Job Research Automation — Plan

A plan for extending the existing CV / cover-letter system with job aggregation,
matching, and package generation. Final submission stays manual.

**Phase 0 (cleanup) must land before any new pipeline work begins.** The current
foundation has enough drift and duplication that adding sub-agents and scrapers
on top would amplify the mess. Clean first, then build.

## Goal

Run a single command (or trigger phrase) and get a curated INBOX of jobs with
tailored CV + cover letter ready to review and submit by hand.

## Phase 0 — Cleanup (do this first)

This list is evidence-based after a full read of the repo. Earlier drafts
overstated several problems; the items below are the ones with concrete file
references and an obvious fix. Order is most-pain-per-effort.

### Things that are already fine — do not touch

- **`tools/lib/` is a real library.** Eight focused modules (`workflow`, `api`,
  `resume`, `tracker`, `templates`, `config`, `paths`, `validation`) with clear
  responsibilities and no cross-duplication. Sub-agents will `import` this
  directly, not shell out.
- **Tests encode intent, not smoke.** `tests/test_resume.py` covers role
  routing, keyword dedup, synonym handling. `tests/test_workflow.py` covers
  dry-run, template filling, placeholder warnings. Keep extending this pattern.
- **CLI tools (`apply.py`, `resume.py`, `status.py`) are thin wrappers over
  `lib/`.** No refactor needed.
- **`browser-harness` integration** — leave it.
- **`applications/active/<slug>/` layout** — fine as a *view*.

### 1. Skill directory dedup ✓

`.claude/skills/job-applier/` and `.agents/skills/job-applier/` are two real
copies of the same 120-line SKILL.md. Recent "sync:" commits show manual
synchronization that will rot. `*-workspace/` directories are abandoned
iteration-1 snapshots from skill-creator with nothing live in them.

→ Pick `.claude/skills/` as canonical. Symlink `.agents/skills/` entries to
  `.claude/skills/` (matching how `humanizer` and `skill-creator` already work).
  Delete `job-applier-workspace/` and `linkedin-workspace/` outright.
  Update `skills-lock.json` so it actually reflects installed skills (currently
  only lists 2 of 4).

**Done.** Resolved in the opposite direction the plan suggested: `.agents/` is
canonical (matching the existing `humanizer` / `skill-creator` symlinks);
`.claude/skills/` symlinks into it. `*-workspace/` directories removed.
`skills-lock.json` left alone — it only tracks github-sourced skills, so its
"incomplete" appearance was wrong.

### 2. Tracker primary key is fragile ✓

`tools/lib/tracker.py` keys applications on `(company.lower(), position.lower())`.
"Caruso" vs "Caruso Corp" silently collide; the same JD pasted twice creates
two directory folders with one tracker row. There is no concept of a
source-side job ID, which is exactly what the scrape pipeline will need for
dedup.

→ Add `job_id` and `source` fields to `ApplicationRecord`. Primary key becomes
  `(source, job_id)` when present, falling back to the current key for manually
  pasted JDs. Add a "seen IDs" set per source so the scraper can dedupe before
  scoring.

**Done.** `ApplicationRecord` extended with `job_id`, `source`, `url`. Tracker
version bumped to 5.1. `upsert_active_application` keys on `(source, job_id)`
when both present, else `(company.lower(), position.lower())`. `seen_jobs` set
+ `is_seen()`/`mark_seen()` helpers added. Covered by `tests/test_workflow.py`.

### 3. Reactive Resume is load-bearing for "JSON → PDF" ✓

If RR changes or goes down, the pipeline halts. `tools/fix_cuid2_ids.py` exists
solely as a band-aid for their CUID2 ID schema fragility. `reactive_resume.py
push` has no dry-run — asymmetric with `apply.py`.

→ Render PDF locally. Typst is the recommended option (best typography per
  unit of effort, single binary, good JSON-driven templating). WeasyPrint is
  the alternative if HTML/CSS templates are preferred. Keep RR as an *optional*
  export path, not a required step. Delete `fix_cuid2_ids.py` once RR is off
  the hot path.

**Done.** Typst chosen. `tools/lib/pdf.py` normalizes Reactive-Resume JSON,
calls Typst with `--root` sandboxing. `templates/resume.typ` rewritten in a
Kami-inspired layout: serif body, ink-blue accent, three-row Role / Actions /
Impact / Metrics per item, compact one-line Skills / Languages / Certifications.
`templates/base-resume.json` carries optional `role` / `actions` / `impact` /
`metrics` fields per entry. `apply.py` renders by default; `tools/reactive_resume.py
push --dry-run` is now optional. `fix_cuid2_ids.py` deleted. Coverage in
`tests/test_pdf.py` (12 tests; typst-dependent smoke tests gated on PATH).

### 4. Merge `match_score.py` + `ats_check.py` ✓

Both scan keywords from `role-configs.json` against the candidate profile, both
do regex matching with slightly different rubrics, neither shares code. Both
are untested.

→ One `tools/lib/scoring.py` module with two entry points (snippet score for
  stage-1 filter; full-JD ATS coverage for stage-2 validation). Add tests
  alongside the existing `test_resume.py` pattern.

**Done.** `tools/lib/scoring.py` houses shared logic (keyword pattern with
`(?<!\w)..(?!\w)` to fix `C++`/`C#` boundary bugs, role-config loader,
HTML stripping, candidate-text flattening). `match_score.py` and `ats_check.py`
are now thin CLI wrappers. Covered by `tests/test_scoring.py` (11 tests).

### 5. Decide on `templates/quality-framework.md` ✓

The `job-applier` SKILL.md cites it as the final pre-submission gate, but no
code reads or enforces it. Either wire it in or stop referencing it.

→ Either: extend `lib/validation.py` to load the checklist and assert rules
  against the generated cover letter + CV, or remove the reference from
  SKILL.md.

**Done.** Kept the framework. Code-checkable parts (length 180–450 words,
paragraph count, placeholder tokens) now run automatically inside the workflow
via `validate_cover_letter_structure()` and surface as warnings. The semantic
checks (truthfulness against base-resume / LinkedIn profile, tone, no buzzword
stuffing) are called out explicitly as agent-enforced in SKILL.md step 9.

### 6. Pick canonical resume source, demote the others ✓

`templates/base-resume.json`, `LinkedIn-CV-Profile.md`, and RR server state
all describe the user. The README and recent commits call LinkedIn "source of
truth"; the actual structured, diffable, version-controlled file is
`base-resume.json`.

→ `base-resume.json` is canonical. `LinkedIn-CV-Profile.md` gets a top-of-file
  "generated by `linkedin` skill, do not edit" header and becomes a one-way
  import target. RR state is ephemeral output, never read back.

**Done.** `LinkedIn-CV-Profile.md` header flipped to "Generated by the
`linkedin` skill. Do not hand-edit." README updated. AGENTS.md tracker schema
bumped to 5.1 documentation. RR state is treated as ephemeral export.

### Phase 0 status

All six items shipped. Pre-existing test failure
(`test_unfilled_editor_prompts_surface_as_warnings`) remains — `templates/cover-letter.md`
was reworded (`[Add one specific sentence...]` instead of `[One sentence...]`)
but `validate_no_placeholders` still looks for the old tokens. Two-line fix
to either the template or the validator; left untouched per surgical-changes
discipline since it predates Phase 0 work.

### Explicitly dropped from earlier drafts

- **Event log (`events.jsonl`)** — overkill for current scope. The tracker
  with a `job_id` key is enough.
- **New `jobhunt/` Python package** — `tools/lib/` already is one.
- **New `Application` dataclass** — `ApplicationRecord` in `tracker.py` exists;
  extend it (item 2) rather than rebuild.
- **"Tools are a bag of CLIs"** — they're thin wrappers over a real library.
  This was wrong.

### Cleanup order

1. Skill dedup + workspace delete (low risk, immediate hygiene win)
2. Tracker job_id field (unblocks scrape pipeline)
3. Merge scoring modules (small, isolated)
4. Local PDF render (biggest change; removes external dependency)
5. quality-framework decision (cheap; do during PDF work)
6. Canonical resume source (mostly docs + a one-line skill header change)

## Two entry points

**A. "Let's start today's job research session"** → full pipeline
1. Reconcile INBOX (archive submitted / skipped items from the previous run)
2. Scrape LinkedIn + Seek for each configured profile, dedupe against tracker
3. Stage-1 match score on listing snippets → drop anything below cutoff
4. Stage-2: generate CV + cover letter for the top N matches
5. Append rows to `INBOX.md`, report counts

**B. "Apply to this job: <URL or pasted JD>"** → single-job path
- Skip steps 1–3, go straight to packager for that one role
- Same `applications/active/<slug>/` layout, same INBOX row
- This is the existing `job-applier` flow, unchanged

## Architecture

Sequential pipeline. Sub-agents exist for **context isolation**, not parallelism.
The orchestrator never sees raw HTML, full JDs, or generated CV drafts — only
small structured results from each sub-agent. This keeps the main context flat
so sessions can run long and stay cheap to resume.

```
orchestrator (Opus)
  │
  ├─ reconciler        archives [x] / [~] from INBOX.md
  ├─ scraper LinkedIn  returns [{job_id, url, title, company, snippet, posted}]
  ├─ scraper Seek      same shape
  ├─ scorer            returns [{job_id, score, one_line_reason}]
  ├─ packager (×N)     one per accepted job — full CV + cover letter
  └─ inbox writer      appends rows
```

If the run is interrupted mid-`packager` loop:
- already-built packages stay on disk
- unsubmitted job IDs are not yet in the tracker as "seen"
- the next run picks up where this one stopped

## Sub-agents

To be defined in `.claude/agents/`.

| Agent          | Model  | Responsibility                                                                 |
|----------------|--------|--------------------------------------------------------------------------------|
| orchestrator   | Opus   | Routing, sequencing, partial-failure handling                                  |
| `reconciler`   | Haiku  | Parse INBOX.md, move dirs to `archive/submitted` or `archive/skipped`, update tracker |
| `scraper`      | Sonnet | Drive browser-harness, extract listing cards, handle layout quirks             |
| `scorer`       | Sonnet | Semantic match listing snippet vs base resume, score 0–100 + one-line reason   |
| `packager`     | Opus   | Tailor CV, write cover letter, push to Reactive Resume, render PDF             |

Rationale: Opus only on the orchestrator (tiny context) and packager (output a
recruiter sees). Everything upstream runs on cheaper tiers. First knob if budget
tightens later: raise scorer cutoff so fewer packager runs fire.

## Data layout

```
applications/
  active/
    <slug>/                 # one per accepted job
      job.md                # full JD
      meta.json             # {job_id, source, url, company, position, posted, score, score_reason}
      cv.pdf
      cover.md
    INBOX.md                # checkbox list, the single source of truth for submission state
  archive/
    submitted/<slug>/
    skipped/<slug>/
  application-tracker.json  # seen job_ids per source + submission timestamps
```

## INBOX.md convention

```
- [ ] **Senior Python Engineer** @ Acme (score: 82) · [JD](./<slug>/job.md) · [CV](./<slug>/cv.pdf) · [Letter](./<slug>/cover.md) · [Apply ↗](https://...)
- [x] **Backend Dev** @ Globex (score: 78) · ...        ← submitted, will archive
- [~] **Frontend Lead** @ Initech (score: 65) · ...     ← not interested, will archive as skipped
```

Reconciler rules:
- `[x]` → `archive/submitted/`, set `submitted_at` in tracker
- `[~]` → `archive/skipped/`, add job_id to a "never re-suggest" list
- `[ ]` → leave alone

## Search config

`tools/search-config.json`: named profiles, each `{name, keywords, location, remote, experience_level}`.

Keyword derivation flow (`tools/search.py --init`):
1. Read `templates/base-resume.json`
2. Propose 5–10 keyword sets from titles, top skills, seniority signal
3. User prunes / edits
4. Save to config

Reason for human-in-the-loop: a resume lists what you *can* do; job search needs
what you *want to do next*. Only the user can apply that filter.

## Filtering defaults

- **Score cutoff:** 65 / 100 (raise if INBOX floods, lower if it's empty)
- **Per-run packager cap:** 10 (above cutoff but past cap → `backlog.md`)
- **Sources:** LinkedIn, Seek. Indeed deferred (aggressive anti-bot).

## Dedup

Job IDs from the source URL (e.g. LinkedIn's `currentJobId=`, Seek's job slug)
are the stable key. Stored per-source in `application-tracker.json`. Date-based
dedup is brittle because both sites show relative timestamps ("2 days ago").

## Browser-harness usage

- LinkedIn scraping reuses the logged-in profile already wired up
- Seek listings are mostly public, no auth needed
- First successful end-to-end run per site → freeze URL pattern + selectors into
  `agent-workspace/domain-skills/linkedin.com/jobs-search.md` and
  `agent-workspace/domain-skills/seek.com.au/jobs-search.md` so future runs skip
  exploration and go straight to extraction

## Open items / polish

- Whether `packager` should fail soft (skip job, continue loop) or hard (stop run) on render errors
- Backlog promotion UX — how to move a `backlog.md` row into the active queue without re-scraping
- Indeed: revisit after LinkedIn + Seek are stable
- Optional auto-classify by job_id: if user has skipped 3 jobs from the same company, suggest hiding that company from future scrapes
- Optional Slack / email notification when INBOX gets new rows
- Phase 0 item 3 (local PDF) — pick a specific renderer once we start: Typst gives best typography for least effort, WeasyPrint if HTML/CSS templates are preferred
