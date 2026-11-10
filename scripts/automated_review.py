#!/usr/bin/env python3
"""Deterministic, non-executing PR diff review for high-confidence hazards.

This scanner reads a unified diff only. It never checks out or executes PR code.
It is intentionally conservative: findings block auto-merge only when the
pattern is high-confidence; other observations are reported as advisories.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "credential",
        re.compile(
            r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|"
            r"github_pat_[A-Za-z0-9_]{30,}|sk_live_[A-Za-z0-9]{16,}|"
            r"xox[baprs]-[A-Za-z0-9-]{20,}|"
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
        "Possible hard-coded credential or private key in added lines.",
    ),
    (
        "write-all",
        re.compile(r"^\s*permissions:\s*write-all\s*$"),
        "Workflow grants permissions: write-all; use least-privilege job permissions.",
    ),
    (
        "shell-pipe",
        re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b"),
        "Downloads and executes a remote script in one pipeline.",
    ),
    (
        "shell-true",
        re.compile(r"\bshell\s*=\s*True\b"),
        "subprocess shell=True requires careful input validation; review for injection.",
    ),
    (
        "dynamic-eval",
        re.compile(r"\b(?:eval|exec)\s*\("),
        "Dynamic code execution; verify the input is fully trusted.",
    ),
)

UNPINNED_ACTION = re.compile(r"^\s*uses:\s*([^\s]+)@([^\s#]+)")
SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def added_lines(diff: str) -> list[tuple[str, int, str]]:
    path = ""
    line_no = 0
    output: list[tuple[str, int, str]] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,\d+)?", line)
            if match:
                line_no = int(match.group(1)) - 1
        elif line.startswith("+") and not line.startswith("+++"):
            line_no += 1
            output.append((path, line_no, line[1:]))
        elif line.startswith(" "):
            line_no += 1
    return output


def review(diff: str) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    advisories: list[str] = []
    additions = added_lines(diff)
    added_workflow_lines = [
        text for path, _, text in additions if path.startswith(".github/workflows/")
    ]
    has_pr_target = any(
        re.search(r"^\s*pull_request_target\s*:", line)
        for line in added_workflow_lines
    )
    checks_out_pr_head = any(
        re.search(
            r"^\\s*ref:\\s*.*(?:github\\.event\\.pull_request\\.head\\.sha|refs/pull/.*/merge)",
            line,
        )
        for line in added_workflow_lines
    )
    if has_pr_target and checks_out_pr_head:
        blockers.append(
            "A pull_request_target workflow appears to check out untrusted PR code. "
            "Run privileged workflows from the base branch only."
        )

    for path, line_no, content in additions:
        for rule, pattern, message in RULES:
            if pattern.search(content):
                finding = f"- **{rule}** `{path}:{line_no}`: {message}"
                (advisories if rule in {"shell-true", "dynamic-eval"} else blockers).append(finding)

        if path.startswith(".github/workflows/"):
            action = UNPINNED_ACTION.search(content)
            if action and not action.group(1).startswith("./"):
                if not SHA.fullmatch(action.group(2)):
                    blockers.append(
                        f"- **unpinned-action** `{path}:{line_no}`: "
                        f"`{action.group(1)}@{action.group(2)}` is not pinned to a full commit SHA."
                    )

    return blockers, advisories


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    blockers, advisories = review(args.diff.read_text(encoding="utf-8", errors="replace"))
    lines = ["## Automated PR review", ""]
    if blockers:
        lines += ["### Blocking findings", *blockers, ""]
    else:
        lines += ["No high-confidence blocking findings detected.", ""]
    if advisories:
        lines += ["### Manual-review advisories", *advisories, ""]
    lines += [
        "---",
        "This is a deterministic diff scanner, not an AI or correctness proof. "
        "CI tests, performance gates, maintainer authorization, and Vercel checks remain mandatory.",
    ]
    report = "\n".join(lines) + "\n"
    args.report.write_text(report, encoding="utf-8")
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"blocking={'true' if blockers else 'false'}\n")
        output.write(f"finding_count={len(blockers) + len(advisories)}\n")
    with args.summary.open("a", encoding="utf-8") as summary:
        summary.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
