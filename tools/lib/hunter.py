"""Hunter.io contact discovery helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .config import ConfigError, load_env, require_env

API_BASE = "https://api.hunter.io/v2"
# Hosts that are never the hiring company's own domain — ATS application hosts
# plus job-board aggregators. A URL on any of these yields no domain hint, so we
# fall back to company-name search instead of (e.g.) querying Hunter for seek.com
# and getting SEEK's own staff.
_NON_COMPANY_HOSTS = (
    "bamboohr.com",
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobvite.com",
    "seek.com",
    "linkedin.com",
    "hiring.cafe",
    "workingnomads.com",
    "wellfound.com",
    "weworkremotely.com",
)


class HunterError(Exception):
    """Raised when Hunter API calls fail."""


def _http_get_json(url: str) -> dict[str, Any]:
    """GET a JSON URL and return the parsed payload."""
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


_COMPOUND_TLDS = (
    "co.nz",
    "com.au",
    "net.au",
    "org.au",
    "co.uk",
    "org.uk",
    "co.jp",
    "co.za",
    "com.sg",
    "com.br",
)


def _registrable_domain(host: str) -> str:
    """Reduce a host to its apex domain so Hunter (which indexes apex domains)
    finds contacts even when the apply URL points at a careers/jobs subdomain."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in _COMPOUND_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _domain_hint_from_url(url: str | None) -> str | None:
    """Infer a likely company domain from a direct company URL."""
    if not url:
        return None
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    if not host:
        return None
    if any(host.endswith(suffix) for suffix in _NON_COMPANY_HOSTS):
        return None
    return _registrable_domain(host.removeprefix("www."))


def _score_contact(contact: dict[str, Any]) -> int:
    """Rank contacts by outreach suitability."""
    position = str(contact.get("position") or "").casefold()
    department = str(contact.get("department") or "").casefold()
    seniority = str(contact.get("seniority") or "").casefold()
    verification = str(contact.get("verification_status") or "").casefold()
    confidence = int(contact.get("confidence") or 0)

    score = confidence
    if any(token in position for token in ("recruit", "talent", "people", "hiring", "hr")):
        score += 120
    if department == "hr":
        score += 80
    if any(
        token in position
        for token in (
            "engineering manager",
            "head of engineering",
            "director of engineering",
            "vp engineering",
            "cto",
        )
    ):
        score += 90
    if department in {"management", "it"}:
        score += 20
    if seniority == "executive":
        score += 15
    if verification == "valid":
        score += 25
    elif verification == "accept_all":
        score += 10
    if contact.get("linkedin"):
        score += 5
    if contact.get("type") == "personal":
        score += 5
    return score


def _normalize_contact(email: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Hunter email record into the shape we store on disk."""
    verification = email.get("verification") or {}
    contact = {
        "full_name": (email.get("first_name") or "") + (
            (" " + email.get("last_name", "").strip()) if email.get("last_name") else ""
        ),
        "first_name": email.get("first_name"),
        "last_name": email.get("last_name"),
        "email": email.get("value"),
        "position": email.get("position"),
        "department": email.get("department"),
        "seniority": email.get("seniority"),
        "type": email.get("type"),
        "confidence": email.get("confidence"),
        "verification_status": verification.get("status"),
        "linkedin": email.get("linkedin"),
        "phone_number": email.get("phone_number"),
        "sources_count": len(email.get("sources") or []),
    }
    contact["full_name"] = contact["full_name"].strip() or None
    contact["rank_score"] = _score_contact(contact)
    return contact


def _contact_summary(contact: dict[str, Any] | None) -> str | None:
    """Render a one-line summary for one contact."""
    if not contact or not contact.get("email"):
        return None
    name = contact.get("full_name") or contact.get("email")
    position = contact.get("position") or "Contact"
    return f"{name} — {position} <{contact['email']}>"


def top_contacts(application_dir: Path, limit: int = 3) -> list[dict[str, Any]]:
    """Read the top stored contact rows (structured) from an application dir."""
    contacts_json = application_dir / "research" / "contacts.json"
    if not contacts_json.exists():
        return []
    try:
        payload = json.loads(contacts_json.read_text())
    except json.JSONDecodeError:
        return []
    contacts = payload.get("contacts") or []
    if not contacts and payload.get("top_contact"):
        contacts = [payload["top_contact"]]
    return list(contacts[:limit])


def top_contact_summaries(application_dir: Path, limit: int = 3) -> list[str]:
    """Read the top stored contact summaries from an application directory."""
    summaries: list[str] = []
    for contact in top_contacts(application_dir, limit):
        summary = _contact_summary(contact)
        if summary:
            summaries.append(summary)
    return summaries


def _render_contacts_markdown(result: dict[str, Any]) -> str:
    """Render a markdown summary of Hunter contact discovery."""
    lines = [f"# Contact Discovery — {result.get('company', 'Unknown Company')}", ""]
    lines.append(f"- **Status:** {result.get('status', 'unknown')}")
    if result.get("domain"):
        lines.append(f"- **Domain:** {result['domain']}")
    if result.get("reason"):
        lines.append(f"- **Reason:** {result['reason']}")
    top_contacts = result.get("top_contacts") or []
    if top_contacts:
        lines.append("- **Top Contacts:**")
        for contact in top_contacts:
            summary = _contact_summary(contact)
            if summary:
                lines.append(f"  - {summary}")
    elif result.get("top_contact"):
        lines.append(f"- **Best Contact:** {_contact_summary(result['top_contact'])}")
    lines.append("")

    contacts = result.get("contacts") or []
    if contacts:
        lines.extend(
            [
                "| Name | Position | Email | Verification | Confidence |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for contact in contacts:
            lines.append(
                "| "
                + " | ".join(
                    [
                        contact.get("full_name") or "—",
                        contact.get("position") or "—",
                        contact.get("email") or "—",
                        contact.get("verification_status") or "—",
                        str(contact.get("confidence") or "—"),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No suitable contacts found.")

    return "\n".join(lines).rstrip() + "\n"


def discover_company_contacts(
    company: str,
    *,
    root: Path | None = None,
    url: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Query Hunter Domain Search and rank the most suitable contacts."""
    load_env(root)
    api_key = require_env("HUNTER_API_KEY")

    domain_hint = _domain_hint_from_url(url)
    params = {
        "api_key": api_key,
        "limit": str(limit),
        "type": "personal",
        "required_field": "full_name,position",
        # No seniority filter: most recruiters aren't tagged senior/executive,
        # and `executive` department keeps founders/CTOs that _score_contact
        # rewards. Ranking is done by _score_contact, not by the server filter.
        "department": "executive,hr,it,management",
    }
    if domain_hint:
        params["domain"] = domain_hint
    else:
        params["company"] = company

    endpoint = f"{API_BASE}/domain-search?{urlencode(params)}"
    try:
        payload = _http_get_json(endpoint)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HunterError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise HunterError(str(exc.reason)) from exc
    except (OSError, json.JSONDecodeError) as exc:
        # Read timeouts (socket.timeout/TimeoutError), connection resets, and
        # non-JSON bodies aren't URLError subclasses — without this they escape
        # discover_contacts' soft-fail handling and crash the whole workflow.
        raise HunterError(str(exc)) from exc

    if payload.get("errors"):
        message = "; ".join(err.get("details", "unknown error") for err in payload["errors"])
        raise HunterError(message)

    data = payload.get("data") or {}
    contacts = [_normalize_contact(email) for email in data.get("emails") or []]
    contacts.sort(key=lambda item: item.get("rank_score", 0), reverse=True)
    top_contact = contacts[0] if contacts else None

    return {
        "status": "ok",
        "company": company,
        "domain": data.get("domain") or domain_hint,
        "organization": data.get("organization") or company,
        "query": {"company": None if domain_hint else company, "domain": domain_hint},
        "top_contact": top_contact,
        "top_contacts": contacts[:3],
        "contacts": contacts,
    }


def discover_contacts(
    application_dir: Path,
    company: str,
    *,
    root: Path | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Discover contacts for an application and write research artifacts."""
    research_dir = application_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    contacts_json = research_dir / "contacts.json"
    contacts_md = research_dir / "contacts.md"

    try:
        result = discover_company_contacts(company, root=root, url=url)
    except ConfigError as exc:
        result = {
            "status": "skipped",
            "company": company,
            "reason": str(exc),
            "contacts": [],
            "top_contact": None,
        }
    except HunterError as exc:
        result = {
            "status": "error",
            "company": company,
            "reason": str(exc),
            "contacts": [],
            "top_contact": None,
        }

    contacts_json.write_text(json.dumps(result, indent=2) + "\n")
    contacts_md.write_text(_render_contacts_markdown(result))
    return result


def best_contact_summary(application_dir: Path) -> str | None:
    """Read the best stored contact summary from an application directory."""
    summaries = top_contact_summaries(application_dir, limit=1)
    return summaries[0] if summaries else None
