# Job Scoring Rubric

Source of truth for the scoring step of the job-research pipeline. The Agent
subagent reads this file when scoring listings from `--scrape-only` output.

Each listing in that output carries a `full_jd` field — **score against the full
JD**, not just the title/snippet. Use the title for the seniority/off-track
token checks below, but judge fit, stack, and seniority from the full JD body.

## Candidate

**Auckland-based junior-to-intermediate full-stack / AI engineer.** Two tracks:

- **Product engineer**: full-stack / software engineer / developer roles using
  Python, TypeScript, React, Node, Next.js, FastAPI. Product companies / SaaS /
  startups / financial-services tech.
- **AI-native engineer**: LLM apps, agents, AI integration.

Location: NZ local + NZ / AU remote acceptable.

For remote boards, keep globally remote / anywhere roles and NZ / AU / APAC
friendly roles. Drop jobs that are explicitly US-only, Canada-only,
Europe-only, or require work authorization outside NZ/AU.

## Score scale (0-100)

- **85-100** — Strong match. Clean product / AI eng title, no seniority tag (or
  `Junior` / `Intermediate` / `Mid` / `All levels` / `I` / `II`), credible
  product / SaaS / startup employer.
- **75-84** — Borderline OK. Generic "Software Engineer" at an unfamiliar but
  plausible employer; "Developer" with no stack hint.
- **65-74** — Marginal. Include only when there's a clear reason to believe
  the role might fit despite ambiguity.
- **Below 65** — Drop.

## Hard drops (never score >= 65)

### Seniority tokens (case-insensitive, word-boundary match on title)
- `senior`, `lead`, `principal`, `staff`, `architect`, `manager`, `director`,
  `head of`, `founding engineer`
- Any seniority-bracket title that includes `senior` (e.g. "Intermediate -
  Senior", "Mid-Senior")

### Off-track engineering disciplines
- **Data / analytics**: `data engineer`, `data engineering`, `analytics
  engineer`, `data analytics`, `bi engineer`, `etl developer`
- **Integration / configuration / ERP / SOE**: `integration engineer`,
  `configuration engineer`, `application engineer` (when paired with ERP /
  CRM / SAP / Oracle), `soe engineer`
- **Embedded / hardware / flight / GNC / aerospace / defence / mining**
  - Companies: Rocket Lab, Leidos, Lockheed, BAE, Boeing, Raytheon, Lunar
    Outpost, Northrop Grumman
  - Title terms: `flight software`, `gnc`, `embedded`, `firmware`, `hardware`,
    `mining`, `aerospace`, `mechanical`, `defence`
- **Sales / solutions / customer / production / service engineer** — drop
  unless explicit product-SWE context in snippet
- **DevOps / SRE / Platform / Infrastructure / Security / QA / Test / Network
  engineer**

### Non-IC roles
- `pm`, `product manager`, `program manager`, `engineering manager`,
  `recruiter`, `designer`, `marketing`, `sales`

### Location / authorization mismatch (backup only)
The pipeline already runs a location gate on the full JD **before** scoring, so
listings reaching you are location-eligible. Still drop anything that slipped
through and is clearly limited to the United States, Canada, Europe, EMEA,
LATAM, or a specific non-NZ/AU region, or requires US/EU/Canada work
authorization or security clearance.

## Sanity check

Before keeping any listing, ask: *"Would I tell a junior-to-intermediate
product dev to apply here?"* If no, drop it even if no token matched.

## Output schema

Write `/tmp/jobhunting-scores.json`:

```json
{
  "cap": 100,
  "scores": [
    {
      "job_id": "...",
      "source": "seek | hiringcafe | linkedin | workingnomads | wellfound | weworkremotely",
      "title": "...",
      "company": "...",
      "url": "...",
      "score": 90,
      "reason": "<= 15 words"
    }
  ]
}
```

Include only listings with `score >= 65`. Sort by `score` descending.
