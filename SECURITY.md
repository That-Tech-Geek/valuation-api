# Security Policy

## Supported versions

Security fixes are currently accepted for the latest code on the default branch. There are no formal long-term-support release branches yet.

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in public issues, discussions, pull requests, or social media.

Use GitHub's **Private vulnerability reporting** for this repository (Security → Advisories → Report a vulnerability) when available. If private reporting is not enabled, contact the repository maintainer through the contact method listed on the maintainer's GitHub profile and request a private security channel.

Please include:
- A concise description and potential impact.
- Affected commit, version, endpoint, or component.
- Reproduction steps or a proof of concept that does not access third-party data.
- Any suggested mitigation.

Do not include real credentials, customer data, or other people's private information in the report.

## Response expectations

The maintainer will acknowledge a report as soon as reasonably possible, investigate severity and reproducibility, and coordinate a fix and disclosure timeline with the reporter. No fixed response-time SLA is currently promised.

Please allow a reasonable period for remediation before public disclosure. Good-faith security research is appreciated; do not disrupt services, access data that is not yours, or test against third-party systems.

## Deployment boundary

The current API is not an authentication or authorization system. Do not expose an instance directly to the public internet without an independently reviewed authentication, authorization, rate-limiting, and network-isolation layer. Never put production credentials in client-side code or pull-request workflows.
