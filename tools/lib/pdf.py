"""Local PDF rendering for tailored resumes via Typst.

Why local: Reactive Resume is fine as a *viewer*, but pinning the pipeline to
an external service means every render goes through a remote API that's
schema-fragile (see fix_cuid2_ids.py) and breaks the moment the service is
down. Typst renders deterministically from a JSON file in a single subprocess.

The Reactive-Resume-shaped JSON is normalized here into a small flat structure
that the Typst template (templates/resume.typ) consumes verbatim. We don't try
to preserve every visual nuance of Reactive Resume — what we need is an
ATS-readable, recruiter-presentable PDF with the same factual content.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .paths import project_root


class PdfRenderError(Exception):
    """Raised when typst is missing, the template fails, or output is empty."""


# Order in which sections render. Anything not listed here is skipped even if
# present in the JSON (keeps the PDF deterministic when the schema evolves).
_SECTION_ORDER: tuple[tuple[str, str, str], ...] = (
    ("experience",     "Experience",     "experience"),
    ("projects",       "Projects",       "project"),
    ("skills",         "Skills",         "skill"),
    ("education",      "Education",      "education"),
    ("certifications", "Certifications", "certification"),
    ("languages",      "Languages",      "language"),
    ("awards",         "Awards",         "award"),
    ("publications",   "Publications",   "publication"),
    ("volunteer",      "Volunteer",      "volunteer"),
    ("interests",      "Interests",      "interest"),
    ("profiles",       "Profiles",       "profile"),
)


def html_to_text(html: str) -> str:
    """Crude HTML → plain text. Preserves paragraph and bullet line breaks.

    Reactive Resume stores rich-text fields as HTML. Typst doesn't render HTML,
    and we don't want to ship a full HTML-to-Typst transpiler — the only
    formatting the data actually uses is paragraphs, <br>, and the occasional
    <strong>/<em>. Stripping to plain text loses bold/italic but keeps the
    bullet structure (the data uses literal • characters inline).
    """
    if not html:
        return ""
    text = html
    text = re.sub(r"<\s*/?(p|div|li|tr)\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    replacements = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class _Item:
    """Flat shape consumed by templates/resume.typ.

    `role`, `actions`, `impact`, `metrics` are the Kami three-row content
    pattern: short Role line, longer Actions, then quantified Impact, with an
    optional metrics row. When any of those is set, the template renders the
    three-row layout. When none are set, it falls back to bullet `body`. This
    lets entries migrate one at a time instead of in a single big-bang rewrite.
    """

    title: str
    meta: str
    subtitle: str
    body: str
    role: str = ""
    actions: str = ""
    impact: str = ""
    metrics: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "meta": self.meta,
            "subtitle": self.subtitle,
            "body": self.body,
            "role": self.role,
            "actions": self.actions,
            "impact": self.impact,
            "metrics": list(self.metrics),
        }


def _metric_tuple(item: dict) -> tuple[str, ...]:
    metrics = item.get("metrics") or []
    return tuple(str(m) for m in metrics if m)


def _norm_experience(item: dict) -> _Item:
    title = " — ".join(p for p in [item.get("company"), item.get("position")] if p)
    return _Item(
        title=title,
        meta=item.get("period", ""),
        subtitle=item.get("location", ""),
        body=html_to_text(item.get("description", "")),
        role=html_to_text(item.get("role", "")),
        actions=html_to_text(item.get("actions", "")),
        impact=html_to_text(item.get("impact", "")),
        metrics=_metric_tuple(item),
    )


def _norm_project(item: dict) -> _Item:
    website = item.get("website") or {}
    label = website.get("label", "") if isinstance(website, dict) else ""
    return _Item(
        title=item.get("name", ""),
        meta=item.get("period", ""),
        subtitle=label,
        body=html_to_text(item.get("description", "")),
        role=html_to_text(item.get("role", "")),
        actions=html_to_text(item.get("actions", "")),
        impact=html_to_text(item.get("impact", "")),
        metrics=_metric_tuple(item),
    )


def _norm_skill(item: dict) -> _Item:
    keywords = item.get("keywords") or []
    return _Item(
        title=item.get("name", ""),
        meta="",
        subtitle="",
        body=", ".join(keywords),
    )


def _norm_education(item: dict) -> _Item:
    title = " — ".join(p for p in [item.get("school"), item.get("degree")] if p)
    subtitle_parts = [p for p in [item.get("area"), item.get("location")] if p]
    if item.get("grade"):
        subtitle_parts.append(str(item["grade"]))
    # Drop a description that just restates the degree (common drift in
    # Reactive Resume exports — title already shows the degree).
    description = html_to_text(item.get("description", ""))
    if description.strip() == (item.get("degree") or "").strip():
        description = ""
    return _Item(
        title=title,
        meta=item.get("period", ""),
        subtitle=" · ".join(subtitle_parts),
        body=description,
    )


def _norm_certification(item: dict) -> _Item:
    return _Item(
        title=item.get("title", ""),
        meta=item.get("date", ""),
        subtitle=item.get("issuer", ""),
        body=html_to_text(item.get("description", "")),
    )


def _norm_language(item: dict) -> _Item:
    return _Item(
        title=item.get("language", ""),
        meta="",
        subtitle=item.get("fluency", ""),
        body="",
    )


def _norm_award(item: dict) -> _Item:
    return _Item(
        title=item.get("title", ""),
        meta=item.get("date", ""),
        subtitle=item.get("awarder", ""),
        body=html_to_text(item.get("summary", "")),
    )


def _norm_publication(item: dict) -> _Item:
    return _Item(
        title=item.get("name", ""),
        meta=item.get("date", ""),
        subtitle=item.get("publisher", ""),
        body=html_to_text(item.get("description", "")),
    )


def _norm_volunteer(item: dict) -> _Item:
    title = " — ".join(p for p in [item.get("organization"), item.get("position")] if p)
    return _Item(
        title=title,
        meta=item.get("period", ""),
        subtitle=item.get("location", ""),
        body=html_to_text(item.get("description", "") or item.get("summary", "")),
    )


def _norm_interest(item: dict) -> _Item:
    keywords = item.get("keywords") or []
    return _Item(
        title=item.get("name", ""),
        meta="",
        subtitle="",
        body=", ".join(keywords),
    )


def _norm_profile(item: dict) -> _Item:
    network = item.get("network", "")
    username = item.get("username", "")
    return _Item(
        title=network,
        meta="",
        subtitle=username,
        body=item.get("website", "") if isinstance(item.get("website"), str) else "",
    )


_NORMALIZERS = {
    "experience": _norm_experience,
    "project": _norm_project,
    "skill": _norm_skill,
    "education": _norm_education,
    "certification": _norm_certification,
    "language": _norm_language,
    "award": _norm_award,
    "publication": _norm_publication,
    "volunteer": _norm_volunteer,
    "interest": _norm_interest,
    "profile": _norm_profile,
}


def _strip_scheme(url: str) -> str:
    """Drop http(s):// from a display URL. The link target keeps the scheme; the
    rendered text just shows the human-readable host+path so contact lines don't
    wrap mid-protocol."""
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def _normalize_resume(resume: dict) -> dict:
    """Flatten a Reactive-Resume-shaped JSON into what templates/resume.typ expects."""
    basics = resume.get("basics") or {}
    contact: list[str] = []
    for key in ("email", "phone", "location"):
        value = basics.get(key)
        if value:
            contact.append(str(value))
    website = basics.get("website") or {}
    if isinstance(website, dict) and website.get("url"):
        contact.append(_strip_scheme(str(website["url"])))
    for cf in basics.get("customFields") or []:
        link = cf.get("link") or cf.get("text")
        if link:
            contact.append(_strip_scheme(str(link)))

    summary = resume.get("summary") or {}
    summary_hidden = bool(summary.get("hidden"))
    summary_text = "" if summary_hidden else html_to_text(summary.get("content", ""))
    summary_title = summary.get("name") or "Summary"

    sections_in = resume.get("sections") or {}
    sections_out: list[dict] = []
    for key, default_title, kind in _SECTION_ORDER:
        section = sections_in.get(key) or {}
        if section.get("hidden"):
            continue
        items_in = [
            it for it in (section.get("items") or [])
            if not it.get("hidden")
        ]
        if not items_in:
            continue
        normalizer = _NORMALIZERS[kind]
        normalized = [normalizer(it).to_dict() for it in items_in]
        sections_out.append({
            "title": section.get("name") or default_title,
            "items": normalized,
        })

    return {
        "name": basics.get("name", ""),
        "headline": basics.get("headline", ""),
        "contact": contact,
        "summary": summary_text,
        "summary_title": summary_title,
        "sections": sections_out,
    }


def _typst_binary() -> str:
    """Locate the typst CLI on PATH or fail with an actionable message."""
    binary = shutil.which("typst")
    if not binary:
        raise PdfRenderError(
            "typst not found on PATH. Install with `brew install typst` "
            "(macOS) or see https://github.com/typst/typst#installation."
        )
    return binary


def render_resume_pdf(
    resume: dict,
    output_path: Path,
    *,
    template_path: Path | None = None,
    project_dir: Path | None = None,
) -> Path:
    """Render a resume dict to PDF at output_path. Returns the output path.

    `resume` is a Reactive-Resume-shaped dict (the same shape `tools/resume.py`
    emits). We normalize it, write the normalized form to a temp JSON file,
    and shell out to typst.
    """
    root = project_dir or project_root()
    template = template_path or (root / "templates" / "resume.typ")
    if not template.exists():
        raise PdfRenderError(f"Typst template not found: {template}")

    normalized = _normalize_resume(resume)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Typst's `--root` sandboxes file reads to within the project, so the temp
    # data file has to live there too. Use a hidden cache dir at the root.
    tmp_dir = root / ".typst-tmp"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=tmp_dir, delete=False
    ) as tf:
        json.dump(normalized, tf)
        data_path = Path(tf.name)

    try:
        # Typst resolves `json(sys.inputs.data)` relative to --root, so pass
        # the data path as project-relative (with a leading slash → project root).
        rel_data_path = "/" + str(data_path.relative_to(root))
        result = subprocess.run(
            [
                _typst_binary(),
                "compile",
                "--root", str(root),
                "--input", f"data={rel_data_path}",
                str(template),
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PdfRenderError(
                f"typst compile failed (exit {result.returncode}):\n"
                f"{result.stderr.strip()}"
            )
    finally:
        data_path.unlink(missing_ok=True)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise PdfRenderError(f"typst produced no output at {output_path}")
    return output_path


def render_resume_pdf_from_file(
    resume_json_path: Path,
    output_path: Path,
    *,
    template_path: Path | None = None,
    project_dir: Path | None = None,
) -> Path:
    """Convenience: load resume.json from disk, then render."""
    with open(resume_json_path) as f:
        resume = json.load(f)
    return render_resume_pdf(
        resume,
        output_path,
        template_path=template_path,
        project_dir=project_dir,
    )
