"""Unified job application package workflow."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .paths import company_dir, tracker_path as tracker_file
from .pdf import PdfRenderError, render_resume_pdf
from .resume import create_resume, resolve_role
from .templates import render_analysis, render_cover_letter
from .tracker import (
    ApplicationRecord,
    load_tracker,
    save_tracker,
    upsert_active_application,
)
from .validation import (
    validate_cover_letter_structure,
    validate_no_placeholders,
    validate_resume_shape,
)


@dataclass(frozen=True)
class WorkflowOptions:
    """Inputs for creating an application package."""

    project_root: Path
    job_path: Path
    company: str
    position: str
    role: str | None = None
    keywords: tuple[str, ...] = ()
    priority: str = "Medium"
    dry_run: bool = False
    job_id: str | None = None
    source: str | None = None
    url: str | None = None
    render_pdf: bool = True


@dataclass(frozen=True)
class WorkflowResult:
    """Paths and planned actions from the workflow."""

    application_dir: Path
    created_paths: tuple[Path, ...]
    planned_actions: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def create_application_package(options: WorkflowOptions) -> WorkflowResult:
    """Create or preview a complete local application package."""
    root = options.project_root
    job_text = options.job_path.read_text(errors="replace")
    app_dir = company_dir(root, options.company)
    research_dir = app_dir / "research"
    documents_dir = app_dir / "documents"
    resume_path = documents_dir / "resume.json"
    analysis_path = research_dir / "analysis.md"
    job_dest = research_dir / "job-description.md"
    cover_path = documents_dir / "cover-letter.md"
    tracker_path = tracker_file(root)

    role = resolve_role(options.role) if options.role else None
    if options.role and role is None:
        raise ValueError(f"Unknown role: {options.role}")
    resume = create_resume(
        root,
        options.company,
        role=role,
        keywords=list(options.keywords),
    )
    validate_resume_shape(resume)

    pdf_path = documents_dir / "resume.pdf"
    planned = [
        f"Create application directory: {app_dir}",
        f"Copy job description: {job_dest}",
        f"Write analysis scaffold: {analysis_path}",
        f"Write tailored resume JSON: {resume_path}",
        f"Write cover letter draft: {cover_path}",
        f"Upsert tracker entry: {tracker_path}",
    ]
    if options.render_pdf:
        planned.append(f"Render resume PDF: {pdf_path}")
    paths_list: list[Path] = [
        job_dest, analysis_path, resume_path, cover_path, tracker_path
    ]
    if options.render_pdf:
        paths_list.append(pdf_path)
    paths = tuple(paths_list)

    if options.dry_run:
        return WorkflowResult(app_dir, paths, tuple(planned))

    research_dir.mkdir(parents=True, exist_ok=True)
    documents_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(options.job_path, job_dest)
    analysis_path.write_text(
        render_analysis(
            options.company, options.position, job_text, options.keywords, root=root
        )
    )
    with open(resume_path, "w") as f:
        json.dump(resume, f, indent=2)
        f.write("\n")
    cover_path.write_text(
        render_cover_letter(
            options.company,
            options.position,
            root=root,
            keywords=options.keywords,
            job_text=job_text,
        )
    )

    remaining = validate_no_placeholders(cover_path)
    structure_warnings = validate_cover_letter_structure(cover_path)
    warnings_list = [
        f"Unresolved placeholder in cover letter: {token}" for token in remaining
    ] + structure_warnings

    if options.render_pdf:
        # Fail soft: a missing typst install or template hiccup shouldn't lose
        # the rest of the package — the user can re-run after fixing it.
        try:
            pdf_record = render_resume_pdf(
                resume, pdf_path, project_dir=root
            )
            record_pdf_path: str | None = str(
                pdf_record.relative_to(root)
            )
        except PdfRenderError as exc:
            record_pdf_path = None
            warnings_list.append(f"PDF render skipped: {exc}")
    else:
        record_pdf_path = None

    tracker = load_tracker(tracker_path)
    record = ApplicationRecord(
        company=options.company,
        position=options.position,
        date_applied=date.today().isoformat(),
        priority=options.priority,
        pdf_path=record_pdf_path,
        job_id=options.job_id,
        source=options.source,
        url=options.url,
    )
    upsert_active_application(tracker, record)
    save_tracker(tracker_path, tracker)

    return WorkflowResult(app_dir, paths, tuple(planned), tuple(warnings_list))
