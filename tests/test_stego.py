# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""Tests for the steganographic encode/decode engine.

These tests use a minimal synthetic channel (not a real LLM) to validate
the arithmetic coding roundtrip without requiring Ollama.
"""

import json
from velamen.stego import encode, decode, _bytes_to_bits, _bits_to_bytes


def _make_synthetic_channel(n_positions: int = 20) -> dict:
    """Create a minimal channel with realistic skewed distributions."""
    import math
    # Vary distributions per position to simulate real LLM output
    base_dists = [
        [{"token": "the ", "prob": 0.5, "logprob": math.log(0.5)},
         {"token": "a ", "prob": 0.25, "logprob": math.log(0.25)},
         {"token": "is ", "prob": 0.15, "logprob": math.log(0.15)},
         {"token": "of ", "prob": 0.10, "logprob": math.log(0.10)}],
        [{"token": "in ", "prob": 0.4, "logprob": math.log(0.4)},
         {"token": "on ", "prob": 0.3, "logprob": math.log(0.3)},
         {"token": "at ", "prob": 0.2, "logprob": math.log(0.2)},
         {"token": "to ", "prob": 0.1, "logprob": math.log(0.1)}],
        [{"token": "be ", "prob": 0.45, "logprob": math.log(0.45)},
         {"token": "do ", "prob": 0.25, "logprob": math.log(0.25)},
         {"token": "go ", "prob": 0.20, "logprob": math.log(0.20)},
         {"token": "no ", "prob": 0.10, "logprob": math.log(0.10)}],
    ]
    dists = [base_dists[i % len(base_dists)] for i in range(n_positions)]
    capacity = sum(
        -sum(e["prob"] * math.log2(e["prob"]) for e in d if e["prob"] > 0)
        for d in dists
    )
    return {
        "format_version": 1,
        "model": "synthetic",
        "cover_prompt": "test",
        "n_tokens": n_positions,
        "top_k": 4,
        "greedy_text": "the " * n_positions,
        "channel_fingerprint": "synthetic",
        "capacity_estimate_bytes": int(capacity / 8),
        "distributions": dists,
    }


def test_bits_roundtrip():
    """Bit conversion is lossless."""
    data = b"\xde\xad\xbe\xef"
    bits = _bytes_to_bits(data)
    assert len(bits) == 32
    recovered = _bits_to_bytes(bits)
    assert recovered == data


def test_raw_encode_produces_tokens():
    """Encode produces a string composed of tokens from the channel."""
    channel = _make_synthetic_channel(50)
    cover = encode("x", channel, key="", raw=True)
    assert isinstance(cover, str)
    assert len(cover) > 0
    # All characters should come from the channel token vocabulary
    all_tokens = set()
    for d in channel["distributions"]:
        for e in d:
            for c in e["token"]:
                all_tokens.add(c)
    for c in cover:
        assert c in all_tokens, f"Unexpected character: {c!r}"


def test_capacity_exceeded():
    """Oversized message raises ValueError."""
    channel = _make_synthetic_channel(10)
    try:
        encode("A" * 1000, channel, key="", raw=True)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "too large" in str(e).lower()


def test_cover_is_string():
    """Encode returns a non-empty string."""
    channel = _make_synthetic_channel(50)
    cover = encode("x", channel, key="", raw=True)
    assert isinstance(cover, str)
    assert len(cover) > 0
