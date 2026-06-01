#!/usr/bin/env python3
"""ATS keyword coverage check: compare a generated resume.json against a JD.

Exits 0 if coverage meets the threshold, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.keyword_match import compute_ats_coverage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ATS keyword coverage check")
    parser.add_argument("--resume", required=True, help="Path to resume.json")
    parser.add_argument("--jd", required=True, help="Path to job description (text/markdown)")
    parser.add_argument(
        "--critical",
        nargs="*",
        default=[],
        help="Critical keywords that must appear (overrides discovery for the gate)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=80,
        help="Minimum coverage %% to pass (default 80)",
    )
    parser.add_argument(
        "--min-density", type=int, default=2, help="Min occurrences per critical keyword"
    )
    parser.add_argument(
        "--max-density", type=int, default=4, help="Max occurrences before flagging stuffing"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    resume_path = Path(args.resume)
    jd_path = Path(args.jd)
    if not resume_path.exists():
        parser.error(f"Resume not found: {resume_path}")
    if not jd_path.exists():
        parser.error(f"JD not found: {jd_path}")

    result = compute_ats_coverage(
        resume_path,
        jd_path.read_text(),
        critical=args.critical or None,
        threshold=args.threshold,
        min_density=args.min_density,
        max_density=args.max_density,
    )

    report = {
        "resume": str(resume_path),
        "jd": str(jd_path),
        "critical_source": result.critical_source,
        "results": result.results,
        "coverage_pct": result.coverage_pct,
        "threshold": result.threshold,
        "passed": result.passed,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        present = sum(1 for r in result.results if r["present"])
        total = len(result.results) or 1
        print(f"ATS Coverage Report ({result.critical_source})")
        print("=" * 40)
        for r in result.results:
            mark = "OK " if r["present"] else "MISS"
            print(f"  [{mark}] {r['keyword']:<30} {r['count']}x   {r['status']}")
        print("-" * 40)
        print(f"Coverage: {present}/{total} critical ({result.coverage_pct}%)")
        print(f"Threshold: {result.threshold}%  ->  {'PASS' if result.passed else 'FAIL'}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
