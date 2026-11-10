#!/usr/bin/env python3
"""Determine whether a PR is an in-scope, versioned product release.

This script only reads GitHub metadata and manifest files. It does not merge,
create tags, deploy, or publish anything.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_EXACT = {
    "README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", ".gitignore",
    "Cargo.toml", "Cargo.lock", "pyproject.toml",
    ".github/CODEOWNERS", ".github/dependabot.yml", ".github/pull_request_template.md",
    ".github/workflows/ci.yml", ".github/workflows/publish-pypi.yml",
    ".github/workflows/auto-merge.yml", ".github/workflows/release-after-merge.yml",
}
ALLOWED_PREFIXES = (
    "src/", "python/", "ingestion/", "tests/", "scripts/", "benches/", "docs/",
)
SIGNIFICANT_PREFIXES = ("src/", "python/", "ingestion/")
SIGNIFICANT_EXACT = {"Cargo.toml", "Cargo.lock", "pyproject.toml"}


def api(path: str):
    token = os.environ["GH_TOKEN"]
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def file_at(repo: str, path: str, ref: str) -> bytes | None:
    encoded = urllib.parse.quote(path, safe="/")
    query = urllib.parse.urlencode({"ref": ref})
    try:
        result = api(f"/repos/{repo}/contents/{encoded}?{query}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return base64.b64decode(result["content"])


def version(data: bytes | None, section: str) -> str | None:
    if data is None:
        return None
    document = tomllib.loads(data.decode("utf-8"))
    if section == "cargo":
        return document["package"]["version"]
    return document["project"]["version"]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: release_eligibility.py PR_NUMBER", file=sys.stderr)
        return 2
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(sys.argv[1])
    pr = api(f"/repos/{repo}/pulls/{pr_number}")
    base = pr["base"]["sha"]
    head = pr["head"]["sha"]
    if pr["base"]["ref"] != "main":
        print("HOLD: only PRs targeting main are eligible.")
        return 1

    files = []
    page = 1
    while True:
        batch = api(f"/repos/{repo}/pulls/{pr_number}/files?per_page=100&page={page}")
        files.extend(item["filename"] for item in batch)
        if len(batch) < 100:
            break
        page += 1

    outside = [
        path for path in files
        if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES)
    ]
    if outside:
        print("HOLD: out-of-scope files: " + ", ".join(outside))
        return 1

    significant = [
        path for path in files
        if path in SIGNIFICANT_EXACT or path.startswith(SIGNIFICANT_PREFIXES)
    ]
    if not significant:
        print("HOLD: no meaningful engine, SDK, ingestion, or package change.")
        return 1

    cargo_base = version(file_at(repo, "Cargo.toml", base), "cargo")
    cargo_head = version(file_at(repo, "Cargo.toml", head), "cargo")
    py_base = version(file_at(repo, "pyproject.toml", base), "python")
    py_head = version(file_at(repo, "pyproject.toml", head), "python")

    if not cargo_head or not py_head or cargo_head != py_head:
        print(f"HOLD: Cargo/Python versions must both exist and match (Cargo={cargo_head}, Python={py_head}).")
        return 1
    if cargo_head == cargo_base or py_head == py_base:
        print(f"HOLD: significant code changes require a coordinated version bump (current {cargo_head}).")
        return 1

    print(json.dumps({
        "eligible": True,
        "release_version": cargo_head,
        "significant_files": significant,
        "changed_files": len(files),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
