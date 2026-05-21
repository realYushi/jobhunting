#!/usr/bin/env python3
"""Render cover-letter.md files to PDF.

Examples:
  python3 tools/cover_letter_pdf.py --file applications/active/Company/documents/cover-letter.md
  python3 tools/cover_letter_pdf.py --queue /tmp/jobhunting-cover-queue.json
  python3 tools/cover_letter_pdf.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.paths import active_dir, project_root  # noqa: E402
from tools.lib.pdf import PdfRenderError, render_cover_letter_pdf_from_file  # noqa: E402
from tools.lib.validation import (  # noqa: E402
    validate_cover_letter_structure,
    validate_no_placeholders,
)


def _cover_paths_from_queue(queue_path: Path) -> list[Path]:
    data = json.loads(queue_path.read_text())
    packages = data if isinstance(data, list) else data.get("packages", [])
    paths: list[Path] = []
    for item in packages:
        cover_path = item.get("cover_path")
        if cover_path:
            paths.append(Path(cover_path))
    return paths


def _cover_paths_from_active(root: Path) -> list[Path]:
    base = active_dir(root)
    if not base.exists():
        return []
    return sorted(base.glob("*/documents/cover-letter.md"))


def _validate_ready(path: Path) -> list[str]:
    warnings: list[str] = []
    placeholders = validate_no_placeholders(path)
    warnings.extend(f"unresolved placeholder: {token}" for token in placeholders)
    warnings.extend(validate_cover_letter_structure(path))
    return warnings


def _render_one(path: Path, output: Path | None, root: Path, force: bool) -> bool:
    if not path.exists():
        print(f"❌ Missing cover letter: {path}", file=sys.stderr)
        return False

    pdf_path = output or path.with_suffix(".pdf")
    if pdf_path.exists() and not force:
        print(f"⏭️  Exists: {pdf_path} (use --force to overwrite)")
        return True

    warnings = _validate_ready(path)
    if warnings:
        print(f"⚠️  {path} is not ready for PDF:", file=sys.stderr)
        for warning in warnings:
            print(f"   - {warning}", file=sys.stderr)
        return False

    try:
        rendered = render_cover_letter_pdf_from_file(
            path,
            pdf_path,
            project_dir=root,
        )
        print(f"✅ {rendered}")
        return True
    except PdfRenderError as exc:
        print(f"❌ Failed to render {path}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Render cover-letter.md to PDF")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Single cover-letter.md to render")
    group.add_argument(
        "--queue",
        type=Path,
        help="Queue JSON from the job research pipeline, e.g. /tmp/jobhunting-cover-queue.json",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Render every applications/active/*/documents/cover-letter.md",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output PDF path for --file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing PDFs")
    args = parser.parse_args()

    if args.output and not args.file:
        parser.error("--output can only be used with --file")

    root = project_root()
    if args.file:
        paths = [args.file]
    elif args.queue:
        paths = _cover_paths_from_queue(args.queue)
    else:
        paths = _cover_paths_from_active(root)

    if not paths:
        print("No cover letters found.", file=sys.stderr)
        return 1

    ok = 0
    for path in paths:
        if _render_one(path, args.output, root, args.force):
            ok += 1

    print(f"\nRendered {ok}/{len(paths)} cover letter PDF(s).")
    return 0 if ok == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
