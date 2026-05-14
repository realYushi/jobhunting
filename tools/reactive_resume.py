#!/usr/bin/env python3
"""CLI: Reactive Resume API client (create, push, PDF, lock, delete)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.api import ApiClient, ApiError, ApiResponse  # noqa: E402
from tools.lib.config import ConfigError, load_env, require_env  # noqa: E402


def _create_client() -> ApiClient:
    api_key = require_env("REACTIVE_RESUME_API_KEY")
    base_url = require_env("REACTIVE_RESUME_BASE_URL")
    return ApiClient(base_url, api_key)


def _unwrap_id(resp: ApiResponse) -> str:
    data = resp.data
    return data if isinstance(data, str) else data["id"]


def list_resumes(client: ApiClient) -> list:
    return client.get("/resumes").data


def get_resume(resume_id: str, client: ApiClient) -> dict:
    return client.get(f"/resumes/{resume_id}").data


def create_resume(
    name: str,
    slug: str,
    tags: list[str],
    client: ApiClient,
    *,
    with_sample: bool = False,
) -> str:
    payload = {
        "name": name,
        "slug": slug,
        "tags": tags,
        "withSampleData": with_sample,
    }
    resume_id = _unwrap_id(client.post("/resumes", payload))
    print(f"Created resume: {resume_id}")
    return resume_id


def update_resume(resume_id: str, resume_data: dict, client: ApiClient) -> dict:
    resp = client.put(f"/resumes/{resume_id}", resume_data)
    print(f"Updated resume: {resume_id}")
    return resp.data


def export_pdf(resume_id: str, output_path: str, client: ApiClient) -> str:
    resp = client.get(f"/resumes/{resume_id}/pdf")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(resp.data)
    print(f"PDF exported: {out}")
    return str(out)


def toggle_lock(resume_id: str, client: ApiClient) -> None:
    current = client.get(f"/resumes/{resume_id}").data
    new_state = not bool(current.get("isLocked"))
    client.post(f"/resumes/{resume_id}/lock", {"isLocked": new_state})
    print(f"Resume {resume_id} isLocked: {new_state}")


def delete_resume(resume_id: str, client: ApiClient) -> None:
    client.delete(f"/resumes/{resume_id}")
    print(f"Deleted resume: {resume_id}")


def push_resume(
    resume_json_path: str,
    name: str,
    slug: str,
    tags: list[str],
    client: ApiClient,
    *,
    pdf_output: str | None = None,
    dry_run: bool = False,
) -> dict:
    resume_path = Path(resume_json_path)
    if not resume_path.exists():
        raise FileNotFoundError(f"{resume_json_path} not found")

    if dry_run:
        return {
            "dry_run": True,
            "would_create": {"name": name, "slug": slug, "tags": tags},
            "would_push_file": str(resume_path),
            "would_export_pdf_to": pdf_output,
        }

    with open(resume_path) as f:
        local_data = json.load(f)

    resume_id = create_resume(name, slug, tags, client)
    remote = get_resume(resume_id, client)
    remote["data"] = local_data
    update_resume(resume_id, remote, client)

    pdf_path = None
    if pdf_output:
        pdf_path = export_pdf(resume_id, pdf_output, client)

    return {
        "resume_id": resume_id,
        "name": name,
        "slug": slug,
        "tags": tags,
        "pdf_path": pdf_path,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reactive Resume API Client")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    sub.add_parser("list", help="List all resumes")

    get_p = sub.add_parser("get", help="Get resume by ID")
    get_p.add_argument("id", help="Resume ID")
    get_p.add_argument("--output", "-o", help="Save to file")

    create_p = sub.add_parser("create", help="Create a new resume")
    create_p.add_argument("--name", required=True, help="Resume name")
    create_p.add_argument("--slug", required=True, help="Unique slug")
    create_p.add_argument("--tags", nargs="*", default=[], help="Tags")
    create_p.add_argument(
        "--with-sample", action="store_true", help="Include sample data"
    )

    push_p = sub.add_parser("push", help="Push local resume.json to Reactive Resume")
    push_p.add_argument("--file", required=True, help="Local resume.json path")
    push_p.add_argument("--name", required=True, help="Resume name")
    push_p.add_argument("--slug", required=True, help="Unique slug")
    push_p.add_argument("--tags", nargs="*", default=[], help="Tags")
    push_p.add_argument("--pdf", help="Export PDF to this path")
    push_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the push without hitting the API",
    )

    update_p = sub.add_parser("update", help="Update resume data from JSON file")
    update_p.add_argument("id", help="Resume ID")
    update_p.add_argument(
        "--file", required=True, help="JSON file with full resume data"
    )

    pdf_p = sub.add_parser("pdf", help="Export resume as PDF")
    pdf_p.add_argument("id", help="Resume ID")
    pdf_p.add_argument("--output", "-o", required=True, help="Output PDF path")

    lock_p = sub.add_parser("lock", help="Toggle resume lock")
    lock_p.add_argument("id", help="Resume ID")

    delete_p = sub.add_parser("delete", help="Delete a resume")
    delete_p.add_argument("id", help="Resume ID")

    return parser


def _dispatch(args: argparse.Namespace, client: ApiClient) -> None:
    if args.command == "list":
        for r in list_resumes(client):
            lock = "🔒" if r.get("isLocked") else "🔓"
            pub = "🌐" if r.get("isPublic") else "🔒"
            print(
                f"  {lock} {pub} {r['id']}  {r['name']}  ({r['slug']})  updated: {r.get('updatedAt', 'N/A')[:10]}"
            )
    elif args.command == "get":
        data = get_resume(args.id, client)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved to {args.output}")
        else:
            print(json.dumps(data, indent=2))
    elif args.command == "create":
        rid = create_resume(
            args.name, args.slug, args.tags, client, with_sample=args.with_sample
        )
        print(f"ID: {rid}")
    elif args.command == "push":
        result = push_resume(
            args.file,
            args.name,
            args.slug,
            args.tags,
            client,
            pdf_output=args.pdf,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
    elif args.command == "update":
        with open(args.file) as f:
            data = json.load(f)
        update_resume(args.id, data, client)
    elif args.command == "pdf":
        export_pdf(args.id, args.output, client)
    elif args.command == "lock":
        toggle_lock(args.id, client)
    elif args.command == "delete":
        delete_resume(args.id, client)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Dry-run push doesn't need credentials — short-circuit before load_env.
    if args.command == "push" and getattr(args, "dry_run", False):
        try:
            result = push_resume(
                args.file, args.name, args.slug, args.tags, None,  # type: ignore[arg-type]
                pdf_output=args.pdf, dry_run=True,
            )
            print(json.dumps(result, indent=2))
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        load_env()
        with _create_client() as client:
            _dispatch(args, client)
    except (ApiError, ConfigError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
