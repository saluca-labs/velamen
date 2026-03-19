# HCTP — Hash-Chain Context Transfer Protocol
## Hermes Protocol Layer v1 | Saluca LLC 2026

---

## Overview

HCTP is a lightweight protocol for transferring conversational context between two
parties over a bandwidth-constrained or covert channel (e.g., Hermes stego). It
achieves three goals:

1. **Minimal bandwidth** — static (shared) history is never retransmitted; only the
   delta travels.
2. **Tamper detection** — a hash chain covers every block; any modification breaks
   the chain.
3. **Predictable data volume** — payload size is bounded by the dynamic window,
   not the total conversation length.

The protocol operates entirely over serialized bytes; Hermes (or any transport) is
responsible for covert encoding. HCTP is the *payload format*.

---

## Concepts

### Context Block
A single conversation turn:
```
{ seq: uint32, role: "user"|"agent", content_hash: sha256hex, summary: utf8 }
```
`content_hash` is SHA-256 of the raw turn text. `summary` is a short (≤120 char)
semantic distillation — the actual plaintext never has to cross the channel.

### Static Section
All blocks both parties have previously acknowledged. Represented as a single
**static root hash** — the running SHA-256 fold over every acknowledged block:
```
root_0  = SHA256(b"hctp-genesis-v1")
root_n  = SHA256(root_{n-1} || SHA256(serialize(block_n)))
```
Transmitting the static root costs exactly 32 bytes regardless of history length.

### Dynamic Section
New blocks since the last acknowledged sync. These are the only blocks that travel
as payload. Compressed with zlib level 9 after JSON serialization.

### Combined Hash
```
combined = SHA256(static_root || dynamic_compressed_bytes)
```
Authenticates the full packet — static alignment + dynamic payload together.

---

## Wire Format

### Sync Packet (what Hermes carries)
```
┌─────────────────────────────────────────────────────────────┐
│ version      : 1 byte   (0x01)                              │
│ packet_type  : 1 byte   (0x53 = 'S' = SYNC)                │
│ seq          : 4 bytes  big-endian uint32 (sender's seq)    │
│ static_root  : 32 bytes SHA-256 of acknowledged history     │
│ dynamic_len  : 4 bytes  big-endian uint32                   │
│ dynamic_data : N bytes  zlib-compressed JSON block list     │
│ combined_hash: 32 bytes SHA-256(static_root||dynamic_data)  │
└─────────────────────────────────────────────────────────────┘
Total minimum: 74 bytes + dynamic payload
```

### Ack Packet
```
┌─────────────────────────────────────────────────────────────┐
│ version      : 1 byte   (0x01)                              │
│ packet_type  : 1 byte   (0x41 = 'A' = ACK)                 │
│ seq          : 4 bytes  big-endian uint32 (echoed SYNC seq) │
│ new_root     : 32 bytes updated static root after folding   │
└─────────────────────────────────────────────────────────────┘
Total: 38 bytes (fits in tiny channel)
```

---

## State Machine

```
SENDER                              RECEIVER
  │                                    │
  │── SYNC(seq=N, static_root, delta)─>│
  │                                    │  1. Reject if seq ≤ last_acked_seq (replay)
  │                                    │  2. Reject if seq == last_seen_seq (duplicate)
  │                                    │  3. Verify combined_hash
  │                                    │  4. Verify static_root matches local root
  │                                    │  5. Decompress + ingest dynamic blocks
  │                                    │  6. Fold dynamic into new static root
  │                                    │  7. Record last_seen_seq = seq
  │<── ACK(seq=N, new_root) ──────────│
  │                                    │
  │  8. Verify new_root matches local  │
  │  9. Promote dynamic → static       │
  │  10. Clear dynamic window          │
  │  11. Record last_acked_seq = seq   │
```

After ACK, both sides have the same static root. The dynamic window is empty.
Next SYNC carries only new turns since the ACK.

**Replay / duplicate rules:**
- Receiver maintains `last_acked_seq` (initialized to -1).
- Any SYNC with `seq ≤ last_acked_seq` is silently dropped.
- Any SYNC with `seq == last_seen_seq` and same `static_root` is treated as a
  retransmit: re-send the prior ACK without re-folding.
- `seq` is a uint32. At wraparound (0xFFFFFFFF → 0) both sides MUST re-key
  (start a new session with fresh genesis). Sessions exceeding 4 billion blocks
  are not supported.
- Out-of-order SYNCs (seq > expected but static_root mismatch) are rejected.

---

## Rolling Root — Bandwidth Properties

Wire overhead per SYNC = 74 bytes fixed (header + static_root + combined_hash) + dynamic payload.

| Scenario            | Fixed overhead | Dynamic payload | Total wire   |
|---------------------|---------------|-----------------|--------------|
| 10 turns (all new)  | 74 B          | ~compressed delta | 74 B + delta |
| 1000 turns + 5 new  | 74 B          | ~5 turns compressed | 74 B + ~5T  |
| 1000 turns + 0 new  | 74 B          | 0 B             | 74 B         |

Key property: **fixed overhead is constant regardless of history length.** Once turns are
acknowledged into the static root, they never cross the wire again — only their 32-byte
hash commitment remains.

---

## Semantic Compression

The dynamic payload carries summaries, not raw text. Example block:
```json
{
  "seq": 42,
  "role": "user",
  "content_hash": "a3f9...e2",
  "summary": "asked about Q3 revenue shortfall and attribution"
}
```
A 500-word turn compresses to ~80 bytes on the wire. Full fidelity verification is
possible if the receiver holds the original (hash check). If not, the summary is
the context — "the gist."

---

## Security Properties

| Property                  | Mechanism                                                        |
|---------------------------|------------------------------------------------------------------|
| Confidentiality           | Hermes AEAD (ChaCha20-Poly1305) wraps the full packet           |
| Integrity & authenticity  | Hermes AEAD — `combined_hash` is a redundant pre-AEAD check only|
| Chained ordering          | Hash chain — each root embeds all prior acknowledged roots       |
| Replay rejection          | Receiver tracks `last_acked_seq`; rejects SYNC with seq ≤ last  |
| Tamper evidence           | Any block modification breaks `combined_hash` before AEAD layer |

**Important notes:**
- `combined_hash` is SHA-256 (unkeyed). It adds **no** cryptographic authenticity on its own — an
  attacker who can forge packets can recompute it for any payload. Authenticity and integrity come
  from the Hermes AEAD layer. `combined_hash` is retained as an application-level ordering check
  (detects accidental corruption or protocol bugs before AEAD decryption).
- There is **no non-repudiation** at the HCTP layer. Either party can construct valid-looking
  chains from genesis. Non-repudiation requires signatures bound to long-term identities, which
  is out of scope for this protocol.
- Authentication of the remote endpoint is delegated entirely to the Hermes key establishment
  layer. Without a shared key, all HCTP integrity guarantees are meaningless.

---

## Integration with Hermes

```python
from sync import ContextChain, SyncPacket
import stego, json

chain = ContextChain()
chain.add_turn("user", raw_text="...", summary="asked about X")

packet = chain.build_sync_packet()
payload_bytes = packet.serialize()

# payload_bytes → Hermes encode → cover text
with open("alpha.hchan") as f:
    channel = json.load(f)
cover = stego.encode(payload_bytes.hex(), channel, key="shared-secret")
```

---

## Limitations / Design Choices

- **summary is trusted, not verified** — receiver cannot verify the summary matches
  content_hash without having the original text. This is intentional: we trade
  perfect fidelity for minimal bandwidth. Use content_hash for deferred verification.
- **No fragmentation** — if dynamic payload exceeds channel capacity, split into
  multiple SYNC packets with same static_root, incrementing seq. Reassembly is
  caller's responsibility.
- **No ordering guarantee** — seq number is informational; out-of-order SYNCs are
  detected by static_root mismatch and rejected.
