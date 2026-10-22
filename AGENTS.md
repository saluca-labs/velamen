# AGENTS.md

Instructions for AI coding agents working in this repository.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[crypto,dev]"
```

Python 3.10 or later. `velamen freeze` additionally needs a local Ollama at `http://localhost:11434`; nothing else does.

## Test

```bash
python -m pytest tests/ -v
ruff check velamen/ tests/
python .github/scripts/check_install_docs.py velamen
```

Passing looks like `14 passed` from pytest (as of 2026-10-22), no ruff findings, and `OK: no PyPI install instructions for velamen` from the install-docs check. CI (`.github/workflows/ci.yml`) runs the same on Python 3.10, 3.11 and 3.12.

## Conventions

- Runtime dependency is `requests` only; `cryptography` is an optional extra. Do not add runtime dependencies.
- Ruff rule set is pinned in `pyproject.toml` (`E4, E7, E9, F`); do not widen it in an unrelated change.
- Install instructions must be git installs from `github.com/saluca-labs/velamen`. Never write a PyPI install for this package; the CI check above fails on one.
- No em-dashes in docs. Use a plain hyphen.
- If you change README.md or docs/PROTOCOL.md, regenerate `llms-full.txt` in the same change (README then docs/PROTOCOL.md, each under a `## <path>` heading) or delete it.

## Do not

- Change the `.hchan` format (`format_version`, fingerprint input) or the HCTP wire format without bumping its version and updating docs/PROTOCOL.md.
- Claim the cover text is undetectable or indistinguishable from model output; nothing in the repo measures that.
- Commit `.hchan` files from real runs, secrets, hostnames, internal paths or personal emails.

## Done means

All three commands under Test pass, and any behaviour change is reflected in README.md (and llms-full.txt).
