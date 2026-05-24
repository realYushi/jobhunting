# Batch Pipeline Redesign

Reorder the batch job-research pipeline so every cheap filter runs **before** the
one expensive stage (full-JD fetch), and scoring is **pure-LLM via a Claude Code
subagent** on full JDs — no inline Anthropic SDK call, no deterministic keyword
scorer.

Scope: the **batch pipeline only** (`tools/pipeline.py` + `job-research` skill).
The manual single-JD `job-applier` skill and its `match_score.py` / `ats_check.py`
/ `scoring.py` are out of scope.

## Target phase order

```
1. Reconcile INBOX                      (cheap)   — LinkedIn sync removed
2. Scrape → snippets + scrape-dedup     (cheap)
3. Dedup vs tracker / INBOX / skipped   (cheap)   ← moved up from packaging
4. Fetch full JD for ALL survivors      (EXPENSIVE, parallel browser-harness)
5. Location gate — drop region-locked   (cheap, needs full JD)
6. LLM score full JD → cutoff           (subagent, rubric file)
7. Package CV / cover / PDF for the cap (cap applied here)
8. Write INBOX
```

Phases 1-5 run inside `--scrape-only`. Phase 6 is the scoring subagent. Phases
7-8 run inside `--from-scores`.

## Data flow

```
pipeline.py --scrape-only listings.json
  → listings.json = { profile_summary, cutoff, cap,
                      listings:[{job_id, source, title, company, url,
                                 location, full_jd}] }     # post-dedup, post-location-gate
scoring subagent (Sonnet, reads tools/scoring-rubric.md)
  → scores.json = { cap, scores:[{job_id, score, reason}] }   # >= cutoff only
pipeline.py --from-scores scores.json --listings listings.json
  → join scores ↔ listings on job_id → cap → package → INBOX
```

Full JD text is fetched once in `--scrape-only` and carried in `listings.json`;
`--from-scores` reads it back via `--listings` so packaging never re-fetches.
`scores.json` stays small (the subagent does not echo JD text).

## Changes by file

### `tools/pipeline.py`

1. **Drop LinkedIn sync (Phase 1).** Remove the `sync_linkedin_statuses` block in
   `do_reconcile_and_scrape` (~lines 272-290). Keep the reconcile step.
2. **Move dedup up (Phase 3).** Lift the `_duplicate_reason` filtering loop out of
   `do_package_from_scores` into `run_scrape_only`, running after scrape, before
   fetch. The index builders (`_build_application_key_index`,
   `_build_company_title_index`, `_build_inbox_indexes`, `load_keyset`) and
   `_duplicate_reason` itself are unchanged — only the call site moves.
3. **Move JD fetch up (Phase 4).** In `run_scrape_only`, after dedup, call
   `_fetch_jds_parallel` on **all** survivors and embed `full_jd` per listing in
   the dump. (Previously this ran in packaging, capped to top-N.)
4. **Move location gate up (Phase 5).** Run `_location_eligibility` per fetched
   listing in `run_scrape_only`, dropping region-locked before the dump. Keep the
   cheap `_snippet_location_excluded` pre-filter as a free pre-fetch drop (zero
   risk: STRICT phrases only) so obvious US-only roles never cost a fetch.
5. **Slim packaging (Phases 7-8).** `do_package_from_scores` becomes: load scores
   + `--listings`, join on `job_id`, cap, build each package using the in-hand
   `full_jd`, write INBOX. Remove its dedup loop, JD fetch, and location gate
   (all now upstream). Keep a lightweight final dedup re-check against INBOX only
   (covers rows submitted between scrape-only and from-scores).
6. **Add `--listings` to `--from-scores`.** `run_from_scores` reads the listings
   file to recover `full_jd` + metadata per scored `job_id`.
7. **Remove the inline single-command path.** Delete `run_pipeline` and its
   `score_listings` / keyword usage. `pipeline.py` exposes only `--scrape-only`
   and `--from-scores` (+ existing flags). `--no-fetch-jd` is removed (scoring now
   depends on full JD). Bare `python3 tools/pipeline.py` prints a one-line pointer
   to the orchestrated flow.

### `tools/lib/scorer.py`

- Remove `score_listings`, `_llm_score_batch`, `_build_anthropic_client`,
  `_SCORING_INSTRUCTIONS`, the keyword-fallback block, and the `anthropic` import.
  `scorer.py` is the **only** Anthropic-SDK user in the repo and the SDK is not
  declared in any dependency file, so this removes it from the codebase entirely
  — scoring is driven purely by the Claude Code subagent.
- Keep `ScoreResult`, `build_candidate_context` / `candidate_summary`,
  `filter_by_score`, `sort_by_score`, `load_candidate_profile`.

### `tools/scoring-rubric.md`

- Change "scores listing snippets" → "scores the full JD".
- Trim the location hard-drop section to a backup note (the code location gate in
  Phase 5 now runs before scoring, so the subagent only sees eligible roles).
- Output schema unchanged.

### `.agents/skills/job-research/SKILL.md`

- Rewrite the Phases + How-to-run sections to the new order: Stage 1
  (`--scrape-only` now also dedups + fetches JD + location-gates), Stage 2 (scoring
  subagent on full JD), Stage 3 (`--from-scores … --listings …`: cap + package).
- Remove the "Single-command fallback" / keyword-net section.
- Update the scoring-subagent prompt skeleton to say "score the full JD".

### `tools/lib/linkedin_status.py`

- Becomes unused by the pipeline. Leave in tree (lower blast radius); note it as
  dead-from-pipeline. Its tests stay green.

## Tests

- **`tests/test_scorer.py`** — delete. It tests the removed keyword `score_listings`.
- **`tests/test_pipeline_dedupe.py`** — unaffected; `_duplicate_reason` keeps its
  signature, only the call site moves.
- **`tests/test_linkedin_status.py`** — unaffected; module stays.
- Add a small test that `run_from_scores` joins `scores.json` ↔ `--listings` on
  `job_id` and packages using the embedded `full_jd` (no fetch).

## Cost note (accepted)

Per the design decision: after dedup, **all** new survivors are fetched and
LLM-scored (~50-80 browser fetches + full-JD tokens per run), vs. the old ~10
fetches. No cheap pre-rank. The conservative `_snippet_location_excluded`
pre-filter is the only pre-fetch trim retained.

## Out of scope

- Manual `job-applier` skill, `match_score.py`, `ats_check.py`, `scoring.py`.
- Cover-letter fill subagent (Stage 4) and cover-PDF render (Stage 5) — unchanged.
