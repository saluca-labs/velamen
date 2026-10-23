# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this is

A Python library and CLI that hides a message inside LLM-style cover text by arithmetic
coding over a pre-frozen table of token probabilities (a `.hchan` file). It also carries HCTP,
an unrelated hash-chained context-transfer format. It is a research artifact at version 0.1.0,
not a production system; `velamen freeze` did not produce a usable channel in the one
configuration tested on 2026-10-22 (see the README corrections).

## Read in this order

1. `README.md` - status, install, quickstart, and the two correction notes that bound what works.
2. `velamen/stego.py` - the core: `encode` / `decode`, arithmetic coding, and the crypto.
3. `velamen/channel.py` - `freeze` and `verify`, and the `.hchan` format.
4. `docs/PROTOCOL.md` with `velamen/hctp.py` - HCTP, which shares nothing with the stego path.

## What you can and cannot see

- In this repo: the full library, CLI, tests, one runnable example on a synthetic channel, and
  the HCTP spec. Everything the package does is here; there is no private half.
- Not in this repo: any real `.hchan` channel file, any detectability evaluation of the cover
  text, and any trained or hosted model. `velamen freeze` reaches a local Ollama you provide.

## The only numbers to trust (each with its source)

- 14 tests pass on Python 3.12 (measured 2026-10-22; run them to re-confirm). Source: `tests/`.
- Channel keeps the top 5 tokens per position. Source: `TOP_K` in `velamen/channel.py`.
- HCTP SYNC fixed overhead is 74 bytes. Source: `SyncPacket` in `velamen/hctp.py` (`deserialize`
  rejects anything shorter).
- Encrypted-mode overhead is 36 bytes (4 length, 12 nonce, 16 tag, 4 guard). Source:
  `velamen/stego.py` and the README quickstart correction.
- Key derivation is PBKDF2-HMAC-SHA256, 100,000 iterations, fixed salt `velamen-channel-v1`.
  Source: `_derive_key` in `velamen/stego.py`.
- Capacity estimates are not reproducible from a prompt; two identical freezes gave different
  channels. Source: the README quickstart correction. Exchange the `.hchan` file itself.

Any other number an agent cites about this repo is unsourced until it is traced to a file here.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[crypto,dev]"
```

Python 3.10 or later. `velamen freeze` additionally needs a local Ollama at
`http://localhost:11434`; nothing else does.

## Test

```bash
python -m pytest tests/ -v
ruff check velamen/ tests/
python .github/scripts/check_install_docs.py velamen
```

Passing looks like `14 passed` from pytest (as of 2026-10-22), no ruff findings, and
`OK: no PyPI install instructions for velamen` from the install-docs check. CI
(`.github/workflows/ci.yml`) runs the same on Python 3.10, 3.11 and 3.12.

## Conventions

- Runtime dependency is `requests` only; `cryptography` is an optional extra. Do not add
  runtime dependencies.
- Ruff rule set is pinned in `pyproject.toml` (`E4, E7, E9, F`); do not widen it in an
  unrelated change.
- Install instructions must be git installs from `github.com/saluca-labs/velamen`. Never write
  a PyPI install for this package; the CI check above fails on one.
- No em-dashes in docs. Use a plain hyphen.
- If you change README.md or docs/PROTOCOL.md, regenerate `llms-full.txt` in the same change
  (README then docs/PROTOCOL.md, each under a `## <path>` heading) or delete it.

## Do not

- Change the `.hchan` format (`format_version`, fingerprint input) or the HCTP wire format
  without bumping its version and updating docs/PROTOCOL.md.
- Claim the cover text is undetectable or indistinguishable from model output; nothing in the
  repo measures that.
- Commit `.hchan` files from real runs, secrets, hostnames, internal paths or personal emails.

## Done means

All three commands under Test pass, and any behaviour change is reflected in README.md (and
llms-full.txt).
