#!/usr/bin/env python3
# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
Encrypted Channel Example -- Alice, Bob, and Eve
==================================================
Demonstrates Velamen's encrypted steganographic workflow with two
communicating parties and an eavesdropper, plus the HCTP protocol
for maintaining hash-chained conversation state.

Run from the repo root:
    python examples/encrypted_channel.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from velamen.stego import encode, decode
from velamen.hctp import ContextChain


# ---------------------------------------------------------------------------
# Synthetic channel (same approach as basic_usage.py)
# ---------------------------------------------------------------------------

VOCAB_GROUPS = [
    [("The ", 0.40), ("A ", 0.25), ("This ", 0.20), ("Each ", 0.10), ("One ", 0.05)],
    [("system ", 0.30), ("report ", 0.25), ("model ", 0.20), ("result ", 0.15), ("value ", 0.10)],
    [("shows ", 0.35), ("gives ", 0.25), ("takes ", 0.20), ("holds ", 0.12), ("needs ", 0.08)],
    [("clear ", 0.30), ("strong ", 0.25), ("new ", 0.20), ("major ", 0.15), ("full ", 0.10)],
    [("in ", 0.30), ("on ", 0.25), ("for ", 0.20), ("with ", 0.15), ("from ", 0.10)],
    [("the ", 0.45), ("a ", 0.25), ("its ", 0.15), ("our ", 0.10), ("no ", 0.05)],
    [("data ", 0.30), ("plan ", 0.25), ("work ", 0.20), ("cost ", 0.15), ("risk ", 0.10)],
    [("and ", 0.35), ("but ", 0.25), ("yet ", 0.15), ("then ", 0.15), ("so ", 0.10)],
    [("also ", 0.30), ("now ", 0.25), ("still ", 0.20), ("here ", 0.15), ("once ", 0.10)],
    [("shows ", 0.30), ("means ", 0.25), ("leads ", 0.20), ("keeps ", 0.15), ("meets ", 0.10)],
]


def make_channel(n: int = 200) -> dict:
    dists = []
    for i in range(n):
        group = VOCAB_GROUPS[i % len(VOCAB_GROUPS)]
        dists.append([
            {"token": tok, "prob": p, "logprob": math.log(p)}
            for tok, p in group
        ])
    cap = sum(
        -sum(e["prob"] * math.log2(e["prob"]) for e in d if e["prob"] > 0)
        for d in dists
    )
    return {
        "format_version": 1, "model": "synthetic",
        "cover_prompt": "(demo)", "n_tokens": n, "top_k": 5,
        "greedy_text": "".join(d[0]["token"] for d in dists),
        "channel_fingerprint": "synthetic-demo",
        "capacity_estimate_bytes": int(cap / 8),
        "distributions": dists,
    }


def divider(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

def main() -> None:
    divider("Encrypted Steganographic Channel")
    print("Alice and Bob share a secret key and a frozen channel file.")
    print("Eve intercepts the cover text but does not know the key.\n")

    channel = make_channel(200)
    shared_key = "correct-horse-battery-staple"

    # -- Alice encodes -------------------------------------------------------
    divider("Alice Sends a Message")
    alice_msg = "Rendezvous at noon"
    print(f"  Alice's secret:  {alice_msg!r}")
    print(f"  Shared key:      {shared_key!r}")

    cover = encode(alice_msg, channel, key=shared_key)
    print(f"  Cover text sent: {cover[:60]}...")
    print("\n  (This text travels over the public channel.)")

    # -- Bob decodes ---------------------------------------------------------
    divider("Bob Receives and Decodes")
    bob_result = decode(cover, channel, key=shared_key)
    print(f"  Bob decodes:     {bob_result!r}")
    print(f"  Matches Alice:   {'YES' if bob_result == alice_msg else 'NO'}")
    assert bob_result == alice_msg

    # -- Eve tries -----------------------------------------------------------
    divider("Eve Attempts to Eavesdrop")
    eve_keys = ["password123", "eve-guess", ""]
    for k in eve_keys:
        try:
            eve_result = decode(cover, channel, key=k)
            print(f"  Key {k!r:20s} -> {eve_result!r} (unexpected!)")
        except Exception as exc:
            print(f"  Key {k!r:20s} -> REJECTED ({type(exc).__name__})")
    print("\n  Eve cannot recover the message without the correct key.")

    # -- HCTP conversation state ---------------------------------------------
    divider("HCTP: Hash-Chained Conversation")
    print("Alice and Bob maintain tamper-evident conversation state using")
    print("the HCTP protocol.  Each turn is folded into a hash chain.\n")

    alice_chain = ContextChain()
    bob_chain = ContextChain()

    # Turn 1: Alice speaks
    alice_chain.add_turn("alice", alice_msg, "proposed rendezvous")
    print(f"  Alice adds turn: 'proposed rendezvous'")

    # Turn 2: Bob replies
    bob_reply = "Confirmed. Bring the documents."
    alice_chain.add_turn("bob", bob_reply, "confirmed, bring docs")
    print(f"  Alice adds turn: 'confirmed, bring docs'")

    # Alice sends SYNC to Bob
    sync = alice_chain.build_sync_packet()
    wire = sync.serialize()
    print(f"\n  SYNC packet:     {len(wire)} bytes on the wire")
    print(f"  Packet valid:    {sync.verify()}")

    # Bob ingests and ACKs
    blocks = bob_chain.ingest_sync(sync)
    print(f"  Bob ingested:    {len(blocks)} blocks")
    for b in blocks:
        print(f"    seq={b.seq}  role={b.role:6s}  summary={b.summary!r}")

    ack = bob_chain.build_ack(sync)
    print(f"\n  ACK packet:      {len(ack.serialize())} bytes")
    print(f"  ACK seq:         {ack.seq}")

    # Alice processes ACK -- roots should now match
    alice_chain.acknowledge(ack.seq)
    roots_match = alice_chain.static_root == bob_chain.static_root
    print(f"\n  Alice root:      {alice_chain.static_root.hex()[:24]}...")
    print(f"  Bob root:        {bob_chain.static_root.hex()[:24]}...")
    print(f"  Roots match:     {'YES' if roots_match else 'NO'}")
    assert roots_match, "Chain roots diverged!"

    # -- Wrap up -------------------------------------------------------------
    divider("Scenario Complete")
    print("Summary:")
    print("  * Alice encoded a secret into innocent-looking cover text.")
    print("  * Bob decoded it with the shared key -- perfect recovery.")
    print("  * Eve was unable to decrypt with wrong keys.")
    print("  * HCTP kept both parties' conversation state in sync with")
    print("    a tamper-evident hash chain.\n")


if __name__ == "__main__":
    main()
