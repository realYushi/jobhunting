#!/usr/bin/env python3
"""
Reactive Resume API Client
Creates, updates, exports, and manages resumes via the Reactive Resume REST API.
Reads credentials from .env file in the project root.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        print(
            "Error: No .env file found. Create one with REACTIVE_RESUME_API_KEY and REACTIVE_RESUME_BASE_URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def get_config():
    """Get API configuration from environment."""
    api_key = os.environ.get("REACTIVE_RESUME_API_KEY")
    base_url = os.environ.get(
        "REACTIVE_RESUME_BASE_URL", "https://rxresu.me/api/openapi"
    )

    if not api_key or api_key == "your-api-key-here":
        print("Error: REACTIVE_RESUME_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    return api_key, base_url.rstrip("/")


def api_request(
    method: str, path: str, api_key: str, base_url: str, data: Optional[dict] = None
) -> tuple:
    """Make an API request. Returns (status_code, response_body)."""
    url = f"{base_url}{path}"
    headers = {"x-api-key": api_key}

    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

            if "application/pdf" in content_type:
                return status, raw
            elif raw:
                text = raw.decode("utf-8")
                try:
                    return status, json.loads(text)
                except json.JSONDecodeError:
                    return status, text.strip().strip('"')
            return status, None
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(body_text)
            return e.code, error_data
        except json.JSONDecodeError:
            return e.code, body_text


def list_resumes(api_key: str, base_url: str):
    """List all resumes."""
    status, data = api_request("GET", "/resumes", api_key, base_url)
    if status != 200:
        print(f"Error listing resumes: {status} {data}", file=sys.stderr)
        sys.exit(1)
    return data


def get_resume(resume_id: str, api_key: str, base_url: str):
    """Get full resume data by ID."""
    status, data = api_request("GET", f"/resumes/{resume_id}", api_key, base_url)
    if status != 200:
        print(f"Error getting resume: {status} {data}", file=sys.stderr)
        sys.exit(1)
    return data


def create_resume(
    name: str,
    slug: str,
    tags: list,
    api_key: str,
    base_url: str,
    with_sample: bool = False,
):
    """Create a new resume. Returns the resume ID."""
    payload = {
        "name": name,
        "slug": slug,
        "tags": tags,
        "withSampleData": with_sample,
    }
    status, data = api_request("POST", "/resumes", api_key, base_url, payload)
    if status != 200:
        print(f"Error creating resume: {status} {data}", file=sys.stderr)
        sys.exit(1)
    # API returns the ID as a quoted string
    resume_id = data if isinstance(data, str) else data.get("id")
    print(f"Created resume: {resume_id}")
    return resume_id


def update_resume(resume_id: str, resume_data: dict, api_key: str, base_url: str):
    """Update a resume's data (PUT). Locks must be off."""
    status, data = api_request(
        "PUT", f"/resumes/{resume_id}", api_key, base_url, resume_data
    )
    if status != 200:
        print(f"Error updating resume: {status} {data}", file=sys.stderr)
        sys.exit(1)
    print(f"Updated resume: {resume_id}")
    return data


def export_pdf(resume_id: str, output_path: str, api_key: str, base_url: str):
    """Export resume as PDF."""
    status, data = api_request("GET", f"/resumes/{resume_id}/pdf", api_key, base_url)
    if status != 200:
        print(f"Error exporting PDF: {status} {data}", file=sys.stderr)
        sys.exit(1)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    print(f"PDF exported: {out}")
    return str(out)


def toggle_lock(resume_id: str, api_key: str, base_url: str):
    """Toggle resume lock status."""
    status, data = api_request("POST", f"/resumes/{resume_id}/lock", api_key, base_url)
    if status == 400:
        print(f"Lock toggle failed (resume may already be in desired state): {data}")
        return data
    if status != 200:
        print(f"Error toggling lock: {status} {data}", file=sys.stderr)
        sys.exit(1)
    print(f"Lock toggled for resume: {resume_id}")
    return data


def delete_resume(resume_id: str, api_key: str, base_url: str):
    """Delete a resume. Must be unlocked."""
    status, data = api_request("DELETE", f"/resumes/{resume_id}", api_key, base_url)
    if status != 200:
        print(f"Error deleting resume: {status} {data}", file=sys.stderr)
        sys.exit(1)
    print(f"Deleted resume: {resume_id}")


def push_resume(
    resume_json_path: str,
    name: str,
    slug: str,
    tags: list,
    api_key: str,
    base_url: str,
    pdf_output: Optional[str] = None,
):
    """Full workflow: create resume in Reactive Resume, push data, optionally export PDF."""
    # Load local resume.json
    resume_path = Path(resume_json_path)
    if not resume_path.exists():
        print(f"Error: {resume_json_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(resume_path) as f:
        local_data = json.load(f)

    # Create empty resume
    resume_id = create_resume(name, slug, tags, api_key, base_url)

    # Get the structure (we need the full envelope)
    remote = get_resume(resume_id, api_key, base_url)

    # Merge: keep remote metadata, replace data with local
    remote["data"] = local_data

    # Push updated data
    update_resume(resume_id, remote, api_key, base_url)

    # Export PDF if requested
    pdf_path = None
    if pdf_output:
        pdf_path = export_pdf(resume_id, pdf_output, api_key, base_url)

    # Return metadata for tracking
    return {
        "resume_id": resume_id,
        "name": name,
        "slug": slug,
        "tags": tags,
        "pdf_path": pdf_path,
    }


def main():
    load_env()
    api_key, base_url = get_config()

    parser = argparse.ArgumentParser(description="Reactive Resume API Client")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # list
    sub.add_parser("list", help="List all resumes")

    # get
    get_p = sub.add_parser("get", help="Get resume by ID")
    get_p.add_argument("id", help="Resume ID")
    get_p.add_argument("--output", "-o", help="Save to file")

    # create
    create_p = sub.add_parser("create", help="Create a new resume")
    create_p.add_argument("--name", required=True, help="Resume name")
    create_p.add_argument("--slug", required=True, help="Unique slug")
    create_p.add_argument("--tags", nargs="*", default=[], help="Tags")
    create_p.add_argument(
        "--with-sample", action="store_true", help="Include sample data"
    )

    # push (full workflow)
    push_p = sub.add_parser("push", help="Push local resume.json to Reactive Resume")
    push_p.add_argument("--file", required=True, help="Local resume.json path")
    push_p.add_argument("--name", required=True, help="Resume name")
    push_p.add_argument("--slug", required=True, help="Unique slug")
    push_p.add_argument("--tags", nargs="*", default=[], help="Tags")
    push_p.add_argument("--pdf", help="Export PDF to this path")

    # update
    update_p = sub.add_parser("update", help="Update resume data from JSON file")
    update_p.add_argument("id", help="Resume ID")
    update_p.add_argument(
        "--file", required=True, help="JSON file with full resume data"
    )

    # pdf
    pdf_p = sub.add_parser("pdf", help="Export resume as PDF")
    pdf_p.add_argument("id", help="Resume ID")
    pdf_p.add_argument("--output", "-o", required=True, help="Output PDF path")

    # lock
    lock_p = sub.add_parser("lock", help="Toggle resume lock")
    lock_p.add_argument("id", help="Resume ID")

    # delete
    delete_p = sub.add_parser("delete", help="Delete a resume")
    delete_p.add_argument("id", help="Resume ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        resumes = list_resumes(api_key, base_url)
        for r in resumes:
            lock = "🔒" if r.get("isLocked") else "🔓"
            pub = "🌐" if r.get("isPublic") else "🔒"
            print(
                f"  {lock} {pub} {r['id']}  {r['name']}  ({r['slug']})  updated: {r.get('updatedAt', 'N/A')[:10]}"
            )

    elif args.command == "get":
        data = get_resume(args.id, api_key, base_url)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved to {args.output}")
        else:
            print(json.dumps(data, indent=2))

    elif args.command == "create":
        rid = create_resume(
            args.name, args.slug, args.tags, api_key, base_url, args.with_sample
        )
        print(f"ID: {rid}")

    elif args.command == "push":
        result = push_resume(
            args.file, args.name, args.slug, args.tags, api_key, base_url, args.pdf
        )
        print(json.dumps(result, indent=2))

    elif args.command == "update":
        with open(args.file) as f:
            data = json.load(f)
        update_resume(args.id, data, api_key, base_url)

    elif args.command == "pdf":
        export_pdf(args.id, args.output, api_key, base_url)

    elif args.command == "lock":
        toggle_lock(args.id, api_key, base_url)

    elif args.command == "delete":
        delete_resume(args.id, api_key, base_url)


if __name__ == "__main__":
    main()
