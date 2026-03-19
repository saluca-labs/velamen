# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
Velamen — Distribution Freezer
===============================
Pre-generates and serializes the token probability distributions for a given
cover prompt. The output file becomes the shared channel config -- both encoder
and decoder use the same frozen table, eliminating cross-machine logprob drift.

Protocol:
  - Pre-shared (out of band): key, model name, this frozen .hchan file
  - Per message:              cover_text only
  - Secret:                   key

Usage:
    velamen freeze --prompt "The quarterly review showed that" \\
        --model phi3:mini --tokens 300 --out channel.hchan

    velamen verify channel.hchan
"""

import hashlib
import json
import math
import time
import requests

DEFAULT_OLLAMA_URL = "http://localhost:11434"
TOP_K = 5
FORMAT_VER = 1


def _query_top_k(prompt: str, model: str, ollama_url: str) -> list[dict]:
    """
    Query Ollama /api/chat for top-K token logprobs at the next position.
    Returns [{token, logprob, prob}] sorted by prob descending.
    """
    resp = requests.post(
        f"{ollama_url}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "logprobs": True,
            "top_logprobs": TOP_K,
            "options": {"num_predict": 1},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    logprobs_list = data.get("logprobs", [])
    if not logprobs_list:
        raise RuntimeError("Model returned no logprobs.")

    top = logprobs_list[0].get("top_logprobs", [])
    if not top:
        raise RuntimeError("top_logprobs empty on first token.")

    pairs = [{"token": e["token"], "logprob": e["logprob"]} for e in top]

    total = sum(math.exp(p["logprob"]) for p in pairs)
    for p in pairs:
        p["prob"] = round(math.exp(p["logprob"]) / total, 10)

    pairs.sort(key=lambda x: -x["prob"])
    return pairs


def freeze(
    cover_prompt: str,
    model: str = "phi3:mini",
    n_tokens: int = 200,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    quiet: bool = False,
) -> dict:
    """
    Generate n_tokens distributions by walking the greedy path:
    at each step, take the top-1 token to advance context,
    record the full top-K distribution for that position.

    The greedy path means distributions are fully deterministic
    for a given (model, cover_prompt) pair on any machine.

    Args:
        cover_prompt: Seed text for the channel
        model:        Ollama model name
        n_tokens:     Number of token positions to freeze
        ollama_url:   Ollama API base URL
        quiet:        Suppress progress output

    Returns:
        Channel dict ready to save as .hchan JSON
    """
    context = cover_prompt
    distributions = []
    greedy_tokens = []

    if not quiet:
        print(f"Freezing {n_tokens} positions for model '{model}'...")

    t0 = time.time()
    for i in range(n_tokens):
        if not quiet and i % 10 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (n_tokens - i) / rate if rate > 0 else 0
            print(f"  [{i:3d}/{n_tokens}] {rate:.1f} tok/s  ETA {eta:.0f}s",
                  end="\r", flush=True)

        top = _query_top_k(context, model, ollama_url)
        distributions.append(top)

        top_token = top[0]["token"]
        greedy_tokens.append(top_token)
        context += top_token

    elapsed = time.time() - t0
    greedy_text = "".join(greedy_tokens)

    if not quiet:
        print(f"\nDone. {n_tokens} positions in {elapsed:.1f}s")

    fp_input = json.dumps(distributions, separators=(",", ":"),
                          sort_keys=True).encode()
    fingerprint = hashlib.sha256(fp_input).hexdigest()

    total_bits = sum(
        -math.log2(d[0]["prob"]) if len(d) > 1 else 0
        for d in distributions
    )
    capacity_bytes = int(total_bits / 8)

    return {
        "format_version": FORMAT_VER,
        "model": model,
        "cover_prompt": cover_prompt,
        "n_tokens": n_tokens,
        "top_k": TOP_K,
        "greedy_text": greedy_text,
        "channel_fingerprint": fingerprint,
        "capacity_estimate_bytes": capacity_bytes,
        "distributions": distributions,
    }


def verify(channel: dict) -> bool:
    """Recompute fingerprint and confirm channel integrity."""
    fp_input = json.dumps(
        channel["distributions"], separators=(",", ":"), sort_keys=True
    ).encode()
    computed = hashlib.sha256(fp_input).hexdigest()
    stored = channel.get("channel_fingerprint", "")
    return computed == stored
