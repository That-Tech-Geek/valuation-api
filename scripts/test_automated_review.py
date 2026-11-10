from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from automated_review import review


class AutomatedReviewTests(unittest.TestCase):
    def test_clean_diff_passes(self) -> None:
        blockers, advisories = review(
            "diff --git a/src/lib.rs b/src/lib.rs\n"
            "--- a/src/lib.rs\n+++ b/src/lib.rs\n"
            "@@ -1 +1 @@\n-old\n+pub fn value() -> u32 { 42 }\n"
        )
        self.assertEqual(blockers, [])
        self.assertEqual(advisories, [])

    def test_hard_coded_github_token_blocks(self) -> None:
        blockers, _ = review(
            "diff --git a/config.py b/config.py\n"
            "--- a/config.py\n+++ b/config.py\n"
            "@@ -1 +1 @@\n-old\n+TOKEN = 'ghp_"
            + "A"
            * 36
            + "'\n"
        )
        self.assertTrue(any("credential" in item for item in blockers))

    def test_api_head_sha_does_not_mean_checkout(self) -> None:
        blockers, _ = review(
            "diff --git a/.github/workflows/review.yml b/.github/workflows/review.yml\n"
            "--- a/.github/workflows/review.yml\n+++ b/.github/workflows/review.yml\n"
            "@@ -0,0 +1,5 @@\n"
            "+on:\n+  pull_request_target:\n"
            "+env:\n"
            "+  HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n"
            "+  REF: main\n"
        )
        self.assertEqual(blockers, [])

    def test_pull_request_target_checkout_of_head_blocks(self) -> None:
        blockers, _ = review(
            "diff --git a/.github/workflows/review.yml b/.github/workflows/review.yml\n"
            "--- a/.github/workflows/review.yml\n+++ b/.github/workflows/review.yml\n"
            "@@ -0,0 +1,4 @@\n"
            "+on:\n+  pull_request_target:\n"
            "+      uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n"
            "+        ref: ${{ github.event.pull_request.head.sha }}\n"
        )
        self.assertTrue(any("untrusted PR code" in item for item in blockers))

    def test_unpinned_workflow_action_blocks(self) -> None:
        blockers, _ = review(
            "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
            "--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n"
            "@@ -0,0 +1 @@\n"
            "+      uses: actions/checkout@v4\n"
        )
        self.assertTrue(any("unpinned-action" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()
