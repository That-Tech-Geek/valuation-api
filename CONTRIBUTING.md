# Contributing

Thanks for considering a contribution to `valuation`.

## Before you start

- Read the [README](README.md) and [architecture notes](docs/architecture.md).
- For a substantial change, open an issue first so scope and model behaviour can be agreed before implementation.
- For security vulnerabilities, do **not** open a public issue. Follow [SECURITY.md](SECURITY.md).
- Do not include API keys, PyPI tokens, private financial data, licensed datasets, or other secrets in commits, tests, fixtures, logs, or screenshots.

## Development setup

Requirements: stable Rust toolchain, Python 3.11+, and maturin.

```bash
python -m pip install --upgrade pip maturin pytest pyarrow
python scripts/create_fixture.py
cargo fmt --all -- --check
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
maturin build --release --out dist
python -m pip install dist/*.whl
python -m pytest -q
```

## Pull requests

1. Create a focused branch from `main`.
2. Keep changes small and explain the problem they solve.
3. Add or update tests for behaviour changes, including invalid inputs and numerical edge cases.
4. Update documentation and public API examples when contracts change.
5. Run the checks above before opening a PR.
6. Describe compatibility impact, assumptions, and any known limitations.

Every PR must pass CI and receive maintainer review before merge. Do not merge your own contribution unless the repository's maintainers have explicitly granted that authority.

## Financial-model changes

Changes to DCF mathematics, financial statement mapping, currency handling, or assumptions require special care:

- State the exact formula and sign convention.
- Include a reproducible numerical example with expected output and units.
- Add tests for boundary conditions (for example, terminal growth approaching WACC, negative FCFF, zero/negative shares, and invalid rates).
- Explain whether the change affects existing outputs or the Python/API contract.
- Never describe model output as investment advice or a guaranteed fair value.

## Engineering standards

- Prefer safe Rust; justify any `unsafe` block and document its invariants.
- Avoid network access in request handlers and tests unless a test explicitly isolates it.
- Validate untrusted input at system boundaries.
- Do not log credentials, full environment variables, or sensitive financial data.
- Keep dependencies necessary, maintained, and appropriately licensed.
- Do not commit generated build output, local datasets, or real customer/company data.

## Review and conduct

Be respectful, specific, and evidence-driven. Critique code and ideas, not people. Harassment and discriminatory behaviour are not acceptable.
