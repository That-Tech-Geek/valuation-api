#!/usr/bin/env python3
"""Determine whether a PR is an in-scope, versioned product release."""
from __future__ import annotations

import base64
import json
import os
import re
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
ALLOWED_PREFIXES = ("src/", "python/", "ingestion/", "tests/", "scripts/", "benches/", "docs/")
SIGNIFICANT_PREFIXES = ("src/", "python/", "ingestion/")


def api(path: str):
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
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
    return document["package"]["version"] if section == "cargo" else document["project"]["version"]


def semver(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"release version must be stable SemVer x.y.z, got {value!r}")
    return tuple(int(part) for part in match.groups())


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: release_eligibility.py PR_NUMBER [--merge|--merged]", file=sys.stderr)
        return 2
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(sys.argv[1])
    merged_mode = len(sys.argv) == 3 and sys.argv[2] == "--merged"
    merge_mode = len(sys.argv) == 3 and sys.argv[2] == "--merge"
    pr = api(f"/repos/{repo}/pulls/{pr_number}")
    if merged_mode:
        merge_sha = pr.get("merge_commit_sha")
        if not merge_sha:
            print("HOLD: merged PR has no merge commit SHA.")
            return 1
        merge_commit = api(f"/repos/{repo}/commits/{merge_sha}")
        base, head = merge_commit["parents"][0]["sha"], merge_sha
    else:
        base, head = pr["base"]["sha"], pr["head"]["sha"]
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

    outside = [path for path in files if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES)]
    if outside:
        print("HOLD: out-of-scope files: " + ", ".join(outside))
        return 1

    significant = [path for path in files if path.startswith(SIGNIFICANT_PREFIXES)]
    if not significant:
        # Maintenance PRs can merge after all gates but never trigger a PyPI release.
        if merge_mode or merged_mode:
            print(json.dumps({
                "eligible": True,
                "release": False,
                "reason": "No engine, SDK, or ingestion changes.",
                "changed_files": len(files),
            }))
            return 0
        print("HOLD: no meaningful engine, SDK, or ingestion change.")
        return 1

    cargo_base = version(file_at(repo, "Cargo.toml", base), "cargo")
    cargo_head = version(file_at(repo, "Cargo.toml", head), "cargo")
    py_base_data = file_at(repo, "pyproject.toml", base)
    py_head_data = file_at(repo, "pyproject.toml", head)
    py_base = version(py_base_data, "python")
    py_head = version(py_head_data, "python")

    if py_head_data is None or tomllib.loads(py_head_data.decode("utf-8"))["project"]["name"] != "valuation":
        print("HOLD: PyPI distribution name must remain exactly 'valuation'.")
        return 1
    if not cargo_head or not py_head or cargo_head != py_head:
        print(f"HOLD: Cargo/Python versions must both exist and match (Cargo={cargo_head}, Python={py_head}).")
        return 1
    current = semver(cargo_head)
    previous_cargo, previous_python = semver(cargo_base), semver(py_base)
    if previous_cargo is not None and current <= previous_cargo:
        print(f"HOLD: release version must increase from Cargo {cargo_base} to {cargo_head}.")
        return 1
    if previous_python is not None and current <= previous_python:
        print(f"HOLD: release version must increase from Python {py_base} to {py_head}.")
        return 1

    print(json.dumps({
        "eligible": True,
        "release": True,
        "release_version": cargo_head,
        "significant_files": significant,
        "changed_files": len(files),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
