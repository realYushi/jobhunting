# Scrape Dedup Redesign — date-window watermark

Replace the ever-growing `seen` id-ledger + overlap-stop pagination with a
**per-source last-scrape date watermark** that bounds how far back each source is
fetched. Keep act-on dedup (skipped + tracker + INBOX) as the single source of
truth for "already handled".

Decisions (locked): daily cadence · **per-source** watermark · keep **full**
act-on dedup (`_duplicate_reason`: skipped + tracker + INBOX).

## Why

Two concerns were tangled under "dedup":

1. **Fetch-windowing** — don't re-pull old listings. (Today: `seen` ledger +
   overlap-stop.) → replace with a date window.
2. **Act-on dedup** — don't re-score/re-package a job already in INBOX, tracker,
   or skipped. (Today: `_duplicate_reason` *and* a parallel filter inside
   `smart_scrape`.) → keep, in **one** place.

Date windows cannot replace #2: a live posting stays in the window for weeks, and
a just-skipped job is recent *by definition*, so it would re-appear every run.
But date windows fully replace #1 and let us delete the unbounded ledger and the
overlap-stop machinery.

## Target architecture

```
smart_scrape  →  per-source date window → fetch NEWEST within window
                 + dedup_within_run (collapse same job across keywords/sources)
                 + advance per-source watermark (only on success)
                 ── NO seen ledger, NO skipped/tracker filtering here ──

pipeline P3   →  _dedup_survivors → _duplicate_reason
                 (skipped + tracker + INBOX) — unchanged, already in lib/dedup.py
```

Net: `smart_scrape` stops doing act-on dedup entirely; `_duplicate_reason`
becomes the only "already handled" gate.

## Watermark + window mechanics

The sidecar `application-ledger.json` is **repurposed** from `seen` to:

```json
{ "last_scrape": { "linkedin": "2026-06-01", "seek": "2026-06-01" } }
```

Per run, per source `S`:

```
days   = (today − last_scrape[S]).days     # missing/first run → INITIAL_LOOKBACK (31)
window = max(BUFFER, days + 1)             # BUFFER = 2 (daily cadence)
# ... scrape S with `window` ...
last_scrape[S] = today                     # ONLY after S scrapes without error
```

A source that errors keeps its old watermark, so the next run auto-covers the
gap. This is why per-source matters: one board failing doesn't widen the window
for the others.

`BUFFER` and `INITIAL_LOOKBACK` live in `search-config.json` `defaults`
(`scrape_buffer_days`, `scrape_initial_lookback_days`).

## window → per-source date filter

Date precision varies by board, so the mapping is source-specific:

| Source | Apply `window` via | Per-job date stop? |
|---|---|---|
| linkedin | `f_TPR=r{window*86400}` + keep `sortBy=DD` | no (param bounds it) |
| seek | `daterange =` smallest of {1,3,7,14,31} ≥ window (cap 31) + `sortmode=ListedDate` | no (param bounds it) |
| wellfound | `within_days(posted, window)` filter | yes — stop paginating when a full page is older |
| weworkremotely | `within_days(posted, window)` | yes |
| workingnomads | `within_days(posted, window)` | yes |
| prosple | `within_days(posted, window)` | yes |
| hiringcafe | search-state date filter **(verify field during impl)**; else `within_days` on parsed date | as available |

`within_days(posted, window)` generalizes today's `_is_wellfound_recent` /
`_is_weworkremotely_recent`. Parse the fuzzy text → age in days:
`today/new → 0`, `yesterday → 1`, `Nd / N day[s] ago → N`, `N week[s] ago → N*7`,
`N month[s] ago → N*30`. **`null`/unparseable → return True (keep)** — never
silently drop a job we can't date; act-on dedup catches repeats.

## Changes by file

### `tools/lib/tracker.py`
- Bump `TRACKER_VERSION` → `"8.0"`. Update the version comment (v8 = `seen`
  ledger replaced by `last_scrape` watermark in the sidecar).
- Remove `seen` everywhere: from `empty_tracker`, `load_tracker`, `save_tracker`
  (write watermark to ledger instead), and delete `mark_seen_key`,
  `is_seen_key`, `seen_by_source`. Rename `_load_seen_ledger` →
  `_load_watermark` (returns the `last_scrape` dict, `{}` when absent).
- Add `load_last_scrape(tracker) -> dict[str,str]` and
  `save`/advance helpers, OR a tiny `lib/watermark.py` — implementer's call;
  keep it close to where the ledger path (`_ledger_for`) lives.
- `save_tracker`: ledger doc becomes `{"last_scrape": {...}}` (sorted keys);
  keep the byte-for-byte no-op-write guard.
- `upsert_active_application`: drop the `mark_seen_key(...)` call.
- Migration: the v5.x→v6 `seen_jobs` migration goes away with `seen`. Keep the
  `skipped_jobs` → `skipped` migration. Strip any inline `seen`/`seen_jobs` from
  old files defensively on load.

### `tools/lib/scraper.py`
- Delete `dedupe_listings` (verify no remaining callers first) and the
  `is_seen_key, is_skipped_key` import.

### `tools/lib/smart_scrape.py`
- `smart_scrape(...)`: drop `stop_at_overlap` and all seen/skipped snapshotting
  (`seen_set`, `skipped_set`, `seen_jobs`, the post-scrape filter loop, the
  `store_keyset("seen")`). Load the watermark, compute `window` per source, pass
  it into the URL builders + the recency filter, advance + persist the watermark
  per successful source. Keep `dedup_within_run`. Return value/`ScrapeSummary`:
  drop `already_seen`; `skipped` count is no longer computed here (rename/repurpose
  or drop). Keep `total_found`, `duplicates_within_run`, `new`.
- URL builders (`_linkedin_base_urls`, `_seek_base_urls`) take a `window_days`
  arg and set `f_TPR` / `daterange` from it (replace the hardcoded
  `r2592000` / `daterange=7|31`).
- Add `within_days(posted, window) -> bool`; refactor `_is_wellfound_recent` /
  `_is_weworkremotely_recent` to call it (or replace them). Per-source paginators
  take `window` instead of `seen_jobs`; stop paginating when a page is all older.
- `_collect_listings`: `recent_filter` becomes `lambda p: within_days(p, window)`.

### `tools/pipeline.py`
- `do_reconcile_and_scrape`: call `smart_scrape(profiles=..., max_total=100)`
  without `stop_at_overlap`. Everything else (Phase 3 `_dedup_survivors`) is
  unchanged.

### `tools/search-config.json`
- `defaults`: add `scrape_buffer_days: 2`, `scrape_initial_lookback_days: 31`.

## Tests

- `tests/test_tracker_ledger.py` — rewrite for `last_scrape` (no `seen`); cover:
  watermark round-trips to the sidecar, missing watermark → `{}`, ledger-only
  write doesn't bump `meta.last_updated`, byte-for-byte no-op guard.
- `tests/test_smart_scrape_keywords.py` — URL builders now take `window_days`;
  assert `f_TPR=r{window*86400}` and `daterange` picks the right bucket.
- `tests/test_smart_scrape_quality.py` — update any seen/overlap expectations.
- New `within_days` tests: today/yesterday/`Nd`/`N days ago`/`N weeks ago`/
  `N months ago`/null/garbage, around the window boundary.
- Delete tests asserting `seen`/`mark_seen`/`is_seen`/`seen_by_source`/
  overlap-stop behavior.
- `_duplicate_reason` / `lib/dedup.py` tests are **untouched** (act-on dedup
  unchanged).
- Add a `smart_scrape` test: a source that raises keeps its old watermark;
  a source that succeeds advances it to today.

## Edge cases
- First run / missing watermark → `INITIAL_LOOKBACK` (31d).
- Source error → watermark NOT advanced (gap auto-covered next run).
- Timezone / board indexing lag → absorbed by `BUFFER` (≥2d) and the fact that
  re-fetching is harmless (act-on dedup dedupes).
- `posted` null/unparseable → keep the listing.
- Running twice in one day → `window = max(BUFFER, 0+1)` = BUFFER; harmless
  re-fetch, deduped downstream.

## Out of scope
- `lib/dedup.py` / `_duplicate_reason` (act-on dedup) — unchanged.
- Packaging, scoring, cover-letter, outreach flows.
- The manual `job-applier` / `apply.py` path.

## Verification (success criteria)
- `python3 -m pytest` green; `ruff check tools` clean.
- `application-ledger.json` contains `last_scrape`, not `seen`.
- `grep -rn "seen_by_source\|mark_seen_key\|is_seen_key\|stop_at_overlap" tools`
  → no matches.
- A dry-run `pipeline.py --scrape-only` smoke prints per-source window sizes.
