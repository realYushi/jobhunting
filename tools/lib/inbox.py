"""INBOX.md writer utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InboxRow:
    """A row to write to INBOX.md."""

    title: str
    company: str
    slug: str
    score: int | None = None
    url: str | None = None
    status: str = "[ ]"  # [ ] = active, [x] = submitted, [~] = skipped


def format_row(row: InboxRow) -> str:
    """Format an InboxRow as a markdown checklist item."""
    parts = [
        f"- {row.status} **{row.title}** @ {row.company}",
    ]

    if row.score is not None:
        parts.append(f" (score: {row.score})")

    links = []
    links.append(f"[JD](./active/{row.slug}/research/job-description.md)")
    links.append(f"[CV](./active/{row.slug}/documents/resume.pdf)")
    links.append(f"[Letter](./active/{row.slug}/documents/cover-letter.pdf)")

    if row.url:
        links.append(f"[Apply ↗]({row.url})")

    parts.append(" · ")
    parts.append(" · ".join(links))

    return "".join(parts)


def write_inbox_row(inbox_path: Path, row: InboxRow) -> None:
    """Append a row to INBOX.md, creating the file if needed."""
    inbox_path.parent.mkdir(parents=True, exist_ok=True)

    line = format_row(row) + "\n"

    if inbox_path.exists():
        # Check if the exact row already exists (by company + full title).
        # Use the formatted title/company marker so "Developer" does not
        # accidentally match "Java Developer" at the same company.
        existing = inbox_path.read_text()
        marker = f"**{row.title}** @ {row.company}"
        for existing_line in existing.splitlines():
            if marker in existing_line:
                return  # Already exists, don't duplicate
        with open(inbox_path, "a") as f:
            f.write(line)
    else:
        # Create new INBOX.md with a header
        inbox_path.write_text(f"# Job INBOX\n\n{line}")


def write_inbox_rows(inbox_path: Path, rows: list[InboxRow]) -> None:
    """Append multiple rows to INBOX.md."""
    for row in rows:
        write_inbox_row(inbox_path, row)


def clear_inbox(inbox_path: Path) -> None:
    """Clear all rows from INBOX.md (keep header if present)."""
    if inbox_path.exists():
        inbox_path.write_text("# Job INBOX\n\n")
