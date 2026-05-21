"""Validation helpers for generated application packages."""

from __future__ import annotations

import json
import re
from pathlib import Path


class ValidationError(Exception):
    """Raised when generated application artifacts are unsafe or incomplete."""


def validate_json_file(path: Path) -> None:
    """Raise ValidationError when a file is missing or invalid JSON."""
    if not path.exists():
        raise ValidationError(f"Missing JSON file: {path}")
    try:
        with open(path) as f:
            json.load(f)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc


def validate_resume_shape(resume: dict) -> None:
    """Check the minimum fields Reactive Resume needs from this project."""
    required = ["basics", "sections", "metadata"]
    missing = [key for key in required if key not in resume]
    if missing:
        raise ValidationError(f"Resume missing required keys: {', '.join(missing)}")
    sections = resume.get("sections")
    if not isinstance(sections, dict) or "skills" not in sections:
        raise ValidationError("Resume must include sections.skills")


def validate_no_placeholders(path: Path) -> list[str]:
    """Return unresolved placeholder tokens found in a text file."""
    text = path.read_text(errors="replace") if path.exists() else ""
    placeholders = (
        "[Company Name]",
        "[Job Title]",
        "[YYYY-MM-DD]",
        "[Add one specific sentence",
        "[Paragraph 2 should",
    )
    return [token for token in placeholders if token in text]


# quality-framework.md asks for 200-400 words and 3 paragraphs in the cover
# letter. Word counts include short signoff phrases, so widen to 180-450 to
# avoid noisy warnings on legitimate letters.
COVER_LETTER_MIN_WORDS = 180
COVER_LETTER_MAX_WORDS = 450
COVER_LETTER_EXPECTED_PARAGRAPHS = 3


def validate_cover_letter_structure(path: Path) -> list[str]:
    """Return structural warnings for a generated cover letter.

    Catches the bits of quality-framework.md that code *can* check: length and
    paragraph count. Truthfulness and tone are still on the agent.
    """
    if not path.exists():
        return []

    text = path.read_text(errors="replace")
    # Strip each `<!-- ... -->` block individually. The template has an inline
    # comment on the salutation line, so a first-open/last-close span would
    # delete the entire letter body.
    body_text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    word_count = len(body_text.split())
    paragraphs = [p for p in body_text.strip().split("\n\n") if p.strip()]
    # Drop salutation + signoff one-liners and the **Date:**/**Position:** header
    # so we count the actual body paragraphs.
    body_paragraphs = [
        p for p in paragraphs
        if len(p.split()) > 6
        and "**Date:**" not in p
        and "**Position:**" not in p
        and not p.lstrip().startswith("#")
    ]

    warnings: list[str] = []
    if word_count < COVER_LETTER_MIN_WORDS:
        warnings.append(
            f"Cover letter is short ({word_count} words; target "
            f"{COVER_LETTER_MIN_WORDS}-{COVER_LETTER_MAX_WORDS})."
        )
    elif word_count > COVER_LETTER_MAX_WORDS:
        warnings.append(
            f"Cover letter is long ({word_count} words; target "
            f"{COVER_LETTER_MIN_WORDS}-{COVER_LETTER_MAX_WORDS})."
        )
    if len(body_paragraphs) != COVER_LETTER_EXPECTED_PARAGRAPHS:
        warnings.append(
            f"Cover letter has {len(body_paragraphs)} body paragraph(s); "
            f"target {COVER_LETTER_EXPECTED_PARAGRAPHS}."
        )
    return warnings
