"""Typed identity for jobs across scrapers and manual flows.

The codebase historically dedup'd records via a polymorphic key that returned
either ``("by-id", source, job_id)`` or ``("by-name", company, position)``
based on which fields the caller happened to populate. That coupling caused
silent matching failures (e.g. a tracker row scraped with source+job_id never
matched an InboxItem built without them).

This module makes the choice explicit. Every record carries one of:

- ``BoardKey(source, job_id)`` — scraped from a known job board with a stable
  identifier. Two BoardKeys are equal iff the source and id agree.
- ``ManualKey(company_lc, position_lc)`` — hand-entered or imported without a
  board identifier. Fields are lowercased at construction so equality is
  case-insensitive on company / position.

Construction normalises inputs (lowercasing source, stripping). Equality is
value equality. JSON (de)serialisation is via ``to_dict`` / ``from_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True)
class BoardKey:
    """Identifier for a listing scraped from a known job board."""

    source: str
    job_id: str

    def __post_init__(self) -> None:
        if not self.source or not self.job_id:
            raise ValueError("BoardKey requires non-empty source and job_id")
        # Normalise for case-insensitive equality across callers.
        object.__setattr__(self, "source", self.source.strip().lower())
        object.__setattr__(self, "job_id", str(self.job_id).strip())

    def to_dict(self) -> dict[str, str]:
        return {"kind": "board", "source": self.source, "job_id": self.job_id}


def _norm_manual_field(value: str) -> str:
    """Normalize a company/position field for ManualKey equality.

    Uses casefold + whitespace collapse so that visually-equivalent strings
    (extra spaces, casing differences, locale-specific casefolding like ß→ss)
    produce the same key. Pipeline code that builds (company, title) lookup
    indexes must apply the same normalization.
    """
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class ManualKey:
    """Identifier for a record without a stable board id (manual flow)."""

    company_lc: str
    position_lc: str

    def __post_init__(self) -> None:
        if not self.company_lc or not self.position_lc:
            raise ValueError("ManualKey requires non-empty company and position")
        company = _norm_manual_field(self.company_lc)
        position = _norm_manual_field(self.position_lc)
        if not company or not position:
            raise ValueError("ManualKey requires non-empty company and position")
        object.__setattr__(self, "company_lc", company)
        object.__setattr__(self, "position_lc", position)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": "manual",
            "company_lc": self.company_lc,
            "position_lc": self.position_lc,
        }


JobKey = Union[BoardKey, ManualKey]


def try_manual_key(company: str | None, position: str | None) -> ManualKey | None:
    """Lenient ManualKey constructor: returns None on empty/whitespace input.

    Use at call sites that receive untrusted scraper output or legacy tracker
    data, where the strict ManualKey constructor would otherwise raise.
    """
    if not company or not position:
        return None
    try:
        return ManualKey(company_lc=company, position_lc=position)
    except ValueError:
        return None


def from_dict(data: dict[str, Any]) -> JobKey:
    """Reconstruct a JobKey from its JSON form."""
    kind = data.get("kind")
    if kind == "board":
        return BoardKey(source=data["source"], job_id=data["job_id"])
    if kind == "manual":
        return ManualKey(company_lc=data["company_lc"], position_lc=data["position_lc"])
    raise ValueError(f"Unknown JobKey kind: {kind!r}")


def key_from_args(
    source: str | None,
    job_id: str | None,
    company: str | None,
    position: str | None,
) -> JobKey:
    """Pick the right key variant from loose args.

    Prefers BoardKey when both source and job_id are present, else ManualKey.
    Used to bridge legacy call sites that pass four loose args; new code should
    construct the variant directly.
    """
    if source and job_id:
        return BoardKey(source=source, job_id=str(job_id))
    if company and position:
        return ManualKey(company_lc=company, position_lc=position)
    raise ValueError(
        "key_from_args requires either (source, job_id) or (company, position)"
    )
