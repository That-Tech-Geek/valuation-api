# Open-source security and merge policy

## Trust boundaries

- The `main` branch is the release source of truth. All contributor changes arrive through pull requests.
- Pull-request workflows receive read-only repository permissions. Never expose deployment, PyPI, or production secrets to forked PR code.
- Actions should be pinned to full commit SHAs and granted only the permissions they need.
- Keep generated market data, credentials, local environment files, and private customer data out of Git.
- Security reports belong in GitHub Private Vulnerability Reporting or the private contact path in [SECURITY.md](../SECURITY.md).

## CI merge gates

The CI workflow runs Rust formatting, unit/integration tests, Clippy with warnings denied, Python compilation and package tests, Rust/Python dependency vulnerability audits, PR scope validation, release binary-size checks, and live API startup/latency/RSS/batch correctness benchmarks.

Any failed gate blocks the auto-merge workflow. The workflow runs from the trusted default-branch definition after CI completes; it does not check out or execute PR code. It verifies that the PR remains open, targets `main`, is not a draft or explicitly held, and still points to the exact SHA tested by CI before requesting a squash merge.

## One-time GitHub repository settings (administrator)

GitHub repository settings are not changed by a source-code PR. Before treating this repository as hardened, configure:

1. **Settings → General → Pull Requests:** enable Allow auto-merge; disable merge commits and rebase merges if squash-only history is desired.
2. **Settings → Rules → Rulesets:** create an active ruleset targeting `main`; require pull requests, require the CI check to pass, require branches to be up to date, block force pushes and deletion, and restrict bypass to a deliberate break-glass administrator path.
3. Require at least one approving review and require CODEOWNERS review if independent human approval is desired. Auto-merge will wait for these requirements.
4. **Settings → Code security and analysis:** enable Dependabot alerts, Dependabot security updates, secret scanning, and push protection where available. Enable private vulnerability reporting.
5. Protect PyPI publishing secrets with a dedicated environment and trusted release workflow. Never make them available to pull-request jobs.

Do not use a workflow as a substitute for branch protection: repository rules are enforced by GitHub, not by the YAML file. If auto-merge is disabled at repository level, the automation cannot override that setting.
