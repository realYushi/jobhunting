"""Keyword scoring shared by stage-1 match-score and stage-2 ATS coverage.

Two entry points:

- compute_match_score(candidate_text, required, preferred)
    Stage-1 / pre-tailoring gate. Score the JD's required + preferred terms
    against the candidate's existing profile (LinkedIn-CV-Profile.md +
    base-resume.json) so we don't waste effort tailoring a package we won't
    send. Also surfaces JD red flags.

- compute_ats_coverage(resume_path, jd_text, critical=None, ...)
    Stage-2 / post-tailoring validation. Score the *generated* resume.json
    against the JD's critical keywords (supplied or auto-discovered from
    role-configs.json) to confirm the tailored package will pass an ATS.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import project_root


RED_FLAGS: dict[str, list[str]] = {
    "workload": [
        r"wear (many|multiple) hats",
        r"fast[- ]paced",
        r"hit the ground running",
        r"self[- ]starter",
        r"\bscrappy\b",
        r"comfortable with ambiguity",
        r"thrives? in ambiguity",
    ],
    "culture": [
        r"\brockstar\b",
        r"\bninja\b",
        r"\bguru\b",
        r"work hard,? play hard",
        r"like a family",
        r"unlimited (pto|vacation|leave)",
    ],
    "compensation": [
        r"competitive salary",
        r"equity[- ]heavy",
        r"commission[- ]only",
        r"\bdoe\b",
    ],
}

VERDICTS = [
    (90, "OVERQUALIFIED — flight-risk flag; apply only if comp/scope justify it"),
    (75, "STRONG FIT — apply"),
    (60, "APPLY WITH STRONG COVER LETTER — gaps must be addressed convincingly"),
    (0, "SKIP — unless dream role"),
]


@lru_cache(maxsize=1)
def load_role_configs() -> dict:
    """Read role-configs.json once."""
    cfg_path = project_root() / "tools" / "role-configs.json"
    with open(cfg_path) as f:
        return json.load(f)


def _keyword_pattern(keyword: str) -> str:
    """Case-insensitive regex with word-boundary-like guards for alnum terms.

    `\\b` doesn't behave around `+`/`#` (C++, C#), so we use lookarounds keyed
    on `\\w` instead. Falls back to plain escape for anything weirder.
    """
    if re.match(r"^[\w\s+#.]+$", keyword):
        return r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
    return re.escape(keyword)


def count_occurrences(text: str, keyword: str) -> int:
    return len(re.findall(_keyword_pattern(keyword), text, re.IGNORECASE))


def has_keyword(text: str, keyword: str) -> bool:
    return count_occurrences(text, keyword) > 0


def normalize(keyword: str, synonyms: dict[str, str]) -> str:
    """Lowercase + map known synonym → canonical (so 'tailwind' == 'tailwind css')."""
    k = keyword.lower().strip()
    return synonyms.get(k, k)


def flatten_strings(node: Any) -> list[str]:
    """Recursively collect string leaves from a JSON-ish structure."""
    out: list[str] = []
    if isinstance(node, str):
        if not node.startswith("http") and len(node) >= 2:
            out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(flatten_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(flatten_strings(item))
    return out


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def resume_text(resume_path: Path) -> str:
    """Flatten a resume.json into one searchable string."""
    with open(resume_path) as f:
        resume = json.load(f)
    return strip_html(" ".join(flatten_strings(resume)))


def candidate_text(profile_path: Path, resume_path: Path) -> str:
    """Combine profile markdown + base resume JSON into one keyword-search blob."""
    parts: list[str] = []
    if profile_path.exists():
        parts.append(profile_path.read_text())
    if resume_path.exists():
        with open(resume_path) as f:
            parts.append(json.dumps(json.load(f)))
    return " ".join(parts)


def verdict_for(score: int) -> str:
    for threshold, label in VERDICTS:
        if score >= threshold:
            return label
    return VERDICTS[-1][1]


def scan_red_flags(jd_text: str) -> dict[str, list[tuple[str, int]]]:
    """Surface common JD red-flag phrases plus a missing-salary signal."""
    hits: dict[str, list[tuple[str, int]]] = {}
    for category, patterns in RED_FLAGS.items():
        for pattern in patterns:
            matches = re.findall(pattern, jd_text, re.IGNORECASE)
            if matches:
                hits.setdefault(category, []).append((pattern, len(matches)))
    has_range = bool(re.search(r"\$\s?\d", jd_text)) or bool(
        re.search(r"\d+\s?k\s?-\s?\d+\s?k", jd_text, re.IGNORECASE)
    )
    if not has_range:
        hits.setdefault("compensation", []).append(("no salary range present", 1))
    return hits


@dataclass(frozen=True)
class KeywordMatch:
    required: list[tuple[str, bool]]
    preferred: list[tuple[str, bool]]
    required_pct: int
    preferred_pct: int
    overall_pct: int
    verdict: str


def compute_match_score(
    text: str,
    required: list[str],
    preferred: list[str],
) -> KeywordMatch:
    """Stage-1 keyword gate over the candidate's existing profile.

    Empty lists are treated as 100% to avoid divide-by-zero and to let callers
    pass one side without the other.
    """
    required_results = [(kw, has_keyword(text, kw)) for kw in required]
    preferred_results = [(kw, has_keyword(text, kw)) for kw in preferred]

    req_total = len(required_results) or 1
    pref_total = len(preferred_results) or 1
    req_hit = sum(1 for _, ok in required_results if ok)
    pref_hit = sum(1 for _, ok in preferred_results if ok)
    req_pct = 100 * req_hit / req_total
    pref_pct = 100 * pref_hit / pref_total

    if not preferred:
        overall = req_pct
    elif not required:
        overall = pref_pct
    else:
        overall = req_pct * 0.7 + pref_pct * 0.3

    overall_int = round(overall)
    return KeywordMatch(
        required=required_results,
        preferred=preferred_results,
        required_pct=round(req_pct),
        preferred_pct=round(pref_pct),
        overall_pct=overall_int,
        verdict=verdict_for(overall_int),
    )


def density_status(count: int, min_density: int, max_density: int) -> str:
    if count == 0:
        return "MISSING"
    if count < min_density:
        return f"low (target {min_density}-{max_density}x)"
    if count > max_density:
        return f"high (target {min_density}-{max_density}x, possible stuffing)"
    return "ok"


def discover_jd_keywords(jd_text: str, known: dict[str, str]) -> list[tuple[str, int]]:
    """Find role-config keywords mentioned in the JD, ranked by count."""
    found: list[tuple[str, int]] = []
    for kw in known:
        count = count_occurrences(jd_text, kw)
        if count > 0:
            found.append((kw, count))
    found.sort(key=lambda x: -x[1])
    return found


@dataclass(frozen=True)
class AtsResult:
    results: list[dict[str, Any]]
    coverage_pct: int
    threshold: int
    critical_source: str
    passed: bool


def compute_ats_coverage(
    resume_path: Path,
    jd_text: str,
    critical: list[str] | None = None,
    threshold: int = 80,
    min_density: int = 2,
    max_density: int = 4,
    *,
    discover_top_n: int = 10,
) -> AtsResult:
    """Stage-2 ATS check over a tailored resume.json.

    When `critical` is omitted, we discover the top-N role-config keywords
    present in the JD and use those.
    """
    cfg = load_role_configs()
    synonyms = cfg.get("synonyms", {})
    known = cfg.get("keyword_to_group", {})
    rtext = resume_text(resume_path)

    if critical:
        critical_terms = [k.strip() for k in critical if k.strip()]
        source = "supplied"
    else:
        critical_terms = [kw for kw, _ in discover_jd_keywords(jd_text, known)[:discover_top_n]]
        source = "auto-discovered from role-configs"

    results: list[dict[str, Any]] = []
    seen_norm: set[str] = set()
    for kw in critical_terms:
        norm = normalize(kw, synonyms)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        count = count_occurrences(rtext, kw)
        for alt, canon in synonyms.items():
            if canon == norm and alt != kw.lower():
                count = max(count, count_occurrences(rtext, alt))
        results.append(
            {
                "keyword": kw,
                "count": count,
                "status": density_status(count, min_density, max_density),
                "present": count > 0,
            }
        )

    present_count = sum(1 for r in results if r["present"])
    total = len(results) or 1
    coverage = round(100 * present_count / total)
    return AtsResult(
        results=results,
        coverage_pct=coverage,
        threshold=threshold,
        critical_source=source,
        passed=coverage >= threshold,
    )
