#!/usr/bin/env python3
# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
Velamen -- Complete Steganographic Pipeline Demo
=================================================
Demonstrates encoding secret messages into LLM-like cover text and
decoding them back, using a synthetic channel (no Ollama required).

Run from the repo root:
    python examples/basic_usage.py
"""

import math
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so the example works without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from velamen.stego import encode, decode


# ---------------------------------------------------------------------------
# Synthetic channel builder
# ---------------------------------------------------------------------------

# Word groups that mimic typical LLM vocabulary clusters.  Each position
# draws from a different group so the cover text reads more naturally
# than cycling through the same three distributions.
VOCAB_GROUPS = [
    # Determiners / articles
    [("The ", 0.40), ("A ", 0.25), ("This ", 0.20), ("Each ", 0.10), ("One ", 0.05)],
    # Nouns (subject)
    [("system ", 0.30), ("report ", 0.25), ("model ", 0.20), ("result ", 0.15), ("value ", 0.10)],
    # Verbs
    [("shows ", 0.35), ("gives ", 0.25), ("takes ", 0.20), ("holds ", 0.12), ("needs ", 0.08)],
    # Adjectives / qualifiers
    [("clear ", 0.30), ("strong ", 0.25), ("new ", 0.20), ("major ", 0.15), ("full ", 0.10)],
    # Prepositions
    [("in ", 0.30), ("on ", 0.25), ("for ", 0.20), ("with ", 0.15), ("from ", 0.10)],
    # Determiners variant
    [("the ", 0.45), ("a ", 0.25), ("its ", 0.15), ("our ", 0.10), ("no ", 0.05)],
    # Abstract nouns
    [("data ", 0.30), ("plan ", 0.25), ("work ", 0.20), ("cost ", 0.15), ("risk ", 0.10)],
    # Connectives / transitions
    [("and ", 0.35), ("but ", 0.25), ("yet ", 0.15), ("then ", 0.15), ("so ", 0.10)],
    # Adverbs
    [("also ", 0.30), ("now ", 0.25), ("still ", 0.20), ("here ", 0.15), ("once ", 0.10)],
    # Verbs variant
    [("shows ", 0.30), ("means ", 0.25), ("leads ", 0.20), ("keeps ", 0.15), ("meets ", 0.10)],
]


def make_synthetic_channel(n_positions: int = 200) -> dict:
    """Build a synthetic frozen channel for demonstration purposes.

    In production you would generate this with ``velamen freeze``, which
    queries a local Ollama model to capture real token probability
    distributions.  Here we build plausible distributions by hand so the
    example runs without any external dependencies.
    """
    dists = []
    for i in range(n_positions):
        group = VOCAB_GROUPS[i % len(VOCAB_GROUPS)]
        dist = [
            {"token": tok, "prob": prob, "logprob": math.log(prob)}
            for tok, prob in group
        ]
        dists.append(dist)

    capacity_bits = sum(
        -sum(e["prob"] * math.log2(e["prob"]) for e in d if e["prob"] > 0)
        for d in dists
    )

    return {
        "format_version": 1,
        "model": "synthetic",
        "cover_prompt": "(demo channel -- no real model)",
        "n_tokens": n_positions,
        "top_k": 5,
        "greedy_text": "".join(d[0]["token"] for d in dists),
        "channel_fingerprint": "synthetic-demo",
        "capacity_estimate_bytes": int(capacity_bits / 8),
        "distributions": dists,
    }


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def subheader(title: str) -> None:
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def main() -> None:
    header("Velamen Steganography Demo")
    print("""
Velamen hides secret messages inside natural-looking text by encoding
them into the token *choices* of a frozen LLM probability channel.
An observer sees plausible text; the real message is invisible.
""")

    # -- Channel setup -------------------------------------------------------
    subheader("1. Channel Setup")
    channel = make_synthetic_channel(n_positions=200)
    print(f"  Positions:       {channel['n_tokens']}")
    print(f"  Top-K per pos:   {channel['top_k']}")
    print(f"  Capacity:        ~{channel['capacity_estimate_bytes']} bytes")
    print("  (In production this comes from a .hchan file frozen with Ollama.)")

    # -- Raw mode: encode / decode -------------------------------------------
    subheader("2. Raw Mode (no encryption)")
    print("  Encoding without encryption -- useful for testing and inspection.\n")

    secret = "Attack at dawn"
    cover = encode(secret, channel, key="", raw=True)
    recovered = decode(cover, channel, key="", raw=True)

    print(f"  Secret message:  {secret!r}")
    print(f"  Cover text:      {cover[:72]}...")
    print(f"  Cover length:    {len(cover)} chars")
    print(f"  Decoded message: {recovered!r}")
    print(f"  Match:           {'YES' if recovered == secret else 'NO'}")
    assert recovered == secret, f"Roundtrip failed: {recovered!r}"

    # -- Encrypted mode: encode / decode with shared key ---------------------
    subheader("3. Encrypted Mode (ChaCha20-Poly1305)")
    print("  Now using a shared passphrase. The payload is encrypted with")
    print("  ChaCha20-Poly1305 before being steganographically embedded.\n")

    secret_enc = "Meet at cafe 9pm"
    key = "hunter2"
    cover_enc = encode(secret_enc, channel, key=key)
    recovered_enc = decode(cover_enc, channel, key=key)

    print(f"  Secret message:  {secret_enc!r}")
    print(f"  Shared key:      {key!r}")
    print(f"  Cover text:      {cover_enc[:72]}...")
    print(f"  Decoded message: {recovered_enc!r}")
    print(f"  Match:           {'YES' if recovered_enc == secret_enc else 'NO'}")
    assert recovered_enc == secret_enc

    # -- Wrong key demo -------------------------------------------------------
    subheader("4. Wrong Key Rejection")
    print("  Attempting to decode with the wrong key should fail.\n")

    wrong_key = "wrong-password"
    try:
        bad_result = decode(cover_enc, channel, key=wrong_key)
        print(f"  UNEXPECTED: decoded as {bad_result!r}")
    except Exception as exc:
        print(f"  Correctly rejected: {type(exc).__name__}")
        print(f"  Error detail:       {exc}")

    # -- Capacity demo --------------------------------------------------------
    subheader("5. Capacity Limits")
    print(f"  This channel holds ~{channel['capacity_estimate_bytes']} bytes.")
    print("  Trying to encode a message that exceeds capacity...\n")

    oversized = "X" * (channel["capacity_estimate_bytes"] + 50)
    try:
        encode(oversized, channel, key="key", raw=True)
        print("  UNEXPECTED: no error raised")
    except ValueError as exc:
        print(f"  Correctly refused: {exc}")

    # -- Summary --------------------------------------------------------------
    header("Demo Complete")
    print("""
All tests passed.  Key takeaways:

  * Encode turns secret bytes into innocent-looking token sequences.
  * Decode reverses the process exactly -- lossless roundtrip.
  * With encryption, even someone with the channel file cannot read
    the message without the correct passphrase.
  * The channel's Shannon entropy limits how much data can be hidden.
""")


if __name__ == "__main__":
    main()
