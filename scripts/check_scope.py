#!/usr/bin/env python3
"""Reject PR changes outside the explicitly supported valuation project scope."""
from __future__ import annotations

import subprocess
import sys

ALLOWED_EXACT = {
    "README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", ".gitignore",
    "Cargo.toml", "Cargo.lock", "pyproject.toml",
    ".github/CODEOWNERS", ".github/dependabot.yml", ".github/pull_request_template.md",
    ".github/workflows/ci.yml", ".github/workflows/publish-pypi.yml",
    ".github/workflows/auto-merge.yml", ".github/workflows/release-after-merge.yml",
    ".github/workflows/auto-review.yml",
    ".github/workflows/security-audit.yml", ".github/workflows/auto-merge.yml",
}
ALLOWED_PREFIXES = (
    "src/", "python/", "ingestion/", "tests/", "scripts/", "benches/", "docs/",
)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_scope.py BASE_SHA HEAD_SHA")
    base, head = sys.argv[1:]
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...{head}"], text=True
    ).splitlines()
    out_of_scope = [
        path for path in changed
        if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES)
    ]
    if out_of_scope:
        print("SCOPE GATE FAILED: changes outside the declared v1 project scope:")
        print("\n".join(f"  - {path}" for path in out_of_scope))
        raise SystemExit(1)
    print(f"SCOPE GATE PASSED: {len(changed)} changed files are within the declared valuation scope.")


if __name__ == "__main__":
    main()
