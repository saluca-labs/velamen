# HCTP - Hash-Chain Context Transfer Protocol

velamen implements **draft-ruvalcaba-hctp-01**, the Internet-Draft that specifies HCTP. The
draft is normative; this page summarises it and says where each rule lives in
`velamen/hctp.py`. Where this page and the draft differ, the draft governs. Section numbers
below are the draft's.

HCTP transfers an ordered, append-only sequence of conversational context between two
endpoints. Acknowledged history is a single 32-byte rolling hash (the static root); only the
blocks not yet acknowledged (the dynamic window) are sent. HCTP carries no confidentiality and
no peer authentication of its own: run it inside a transport that provides both. In velamen
that is the encrypted stego channel (called "Hermes" in older notes, implemented by
`velamen/stego.py`), and any authenticated transport such as TLS 1.3 or QUIC works equally.

---

## Context block (Section 3.1)

```
{"content_hash":"<64 lowercase hex>","role":"<1..64 octets>","seq":<uint32>,"summary":"<0..120 code points>"}
```

- `seq`: position in its directional chain, starting at 0.
- `role`: an application label, 1 to 64 octets of UTF-8. It never selects a chain.
- `content_hash`: SHA-256 of the UTF-8 raw turn text, exactly 64 lowercase hex digits.
- `summary`: at most 120 Unicode code points (a character outside the BMP counts once).
- No Unicode normalization is applied anywhere; NFC and NFD forms of the same text hash
  differently.

### Canonical encoding

`canonical(B)` is the RFC 8785 (JCS) serialization of the four-member object:

- members in code-point order (`content_hash`, `role`, `seq`, `summary`), no whitespace;
- strings: only `"`, `\` and U+0000..U+001F are escaped. U+0008, U+0009, U+000A, U+000C and
  U+000D use `\b \t \n \f \r`; the other control characters use `\u00xx` with lowercase hex.
  Everything else, including non-ASCII, `<`, `>`, `&`, U+007F, U+2028 and U+2029, is written
  as raw UTF-8. A string with an unpaired surrogate has no canonical form and is refused;
- `seq`: ASCII digits only, no sign, no leading zero (except `0`), no fraction, no exponent.

Several blocks travel as the canonical array: `[`, the canonical blocks joined by `,`, `]`.

In code: `ContextBlock.canonical_bytes()`, `encode_block_array()`, and `parse_block_array()`,
which accepts decompressed octets only if they are exactly the canonical encoding of a
non-empty array of valid blocks.

**Changed from -00.** velamen 0.1.0 wrote non-ASCII as `\uXXXX` (Python's `json.dumps`
default). Under -01 any block with a non-ASCII role or summary folds to a different root than
it did in 0.1.0. ASCII-only blocks fold to the same roots as before.

---

## Rolling root (Section 4)

```
root_0     = SHA256("hctp-genesis-v1")            15 ASCII octets, no NUL
fold(R, B) = SHA256(R || SHA256(canonical(B)))
```

In code: `genesis_root()` and `fold()`.

---

## Wire format (Section 5)

All integers are big-endian.

SYNC (`SyncPacket`), 74 octets plus `dynamic_len`:

| Field         | Octets      | Content                                               |
|---------------|-------------|-------------------------------------------------------|
| version       | 1           | 0x01                                                  |
| ptype         | 1           | 0x53 ('S')                                            |
| seq           | 4           | seq of the last block in dynamic_data                 |
| static_root   | 32          | sender's static root                                  |
| dynamic_len   | 4           | length of dynamic_data, never zero                    |
| dynamic_data  | dynamic_len | one zlib stream, FDICT clear, of the canonical array  |
| combined_hash | 32          | SHA256(static_root \|\| dynamic_data)                 |

ACK (`AckPacket`), exactly 38 octets: version 0x01, ptype 0x41 ('A'), the echoed seq, and
`new_root`, the receiver's static root after folding.

A transport unit carries exactly one packet and nothing else (Section 10). `parse_packet()`
enforces that and reports a `PacketError.reason` of `too_short`, `unknown_version`,
`unknown_packet_type`, `dynamic_len_too_large` or `length_mismatch`. `dynamic_len` is compared
with the receiver's bound before dynamic_data is read.

---

## Receiver (Sections 6.1, 6.3): `HctpReceiver`

State per directional chain: `local_root`, `last_seen_seq`, `last_block_seq`, `has_seen`,
and `ack_cache` (the cached ACK, the pre-fold root, and the SHA-256 of the accepted SYNC's
octets). `HctpReceiver.receive()` applies the checks in this order:

1. **Framing and version.** Exactly one SYNC filling the transport unit.
2. **Integrity.** combined_hash recomputed over the octets as received.
3. **Replay.** seq below `last_seen_seq` is discarded.
4. **Duplicate.** seq equal to `last_seen_seq`: if the SHA-256 of the received octets equals
   the cached digest, the cached ACK is returned and nothing is folded (a lost ACK); any other
   SYNC with that seq is discarded.
5. **Alignment.** static_root different from `local_root` is fatal: `FatalSessionError`, and
   the session ends.
6. **Ingest validation.** One complete zlib stream with FDICT clear and nothing after it;
   decompressed output within the bound; the octets exactly the canonical non-empty array;
   every block valid; seqs contiguous from `last_block_seq + 1` (or 0); the last block's seq
   equal to the packet seq.
7. **Accept.** Fold, record state, cache `(ACK, pre-fold root, digest)`, return the ACK.

Every non-fatal rejection raises `Rejected` (its `step` names the check) with no state change;
the caller sends nothing. The receiver accepts at least 64 blocks and 65536 decompressed
octets per SYNC (the Section 9 baselines) and refuses to be configured below them.

---

## Sender (Sections 6.1, 6.2, 6.4, 6.5): `HctpSender`

- `add_turn()` assigns the seq when the block is originated. While a SYNC is outstanding the
  window is frozen and new blocks wait in a queue, already numbered.
- `build_sync()` sends the window, or its first part when it exceeds 64 blocks or 65536
  decompressed octets. The static root does not move at send time.
- `receive_ack()` discards an ACK whose seq is not the outstanding one (or not above
  `last_acked_seq`, which is undefined until the first ACK). Otherwise it folds exactly the
  blocks of the outstanding SYNC into a candidate root. If `new_root` differs, the session
  ends with `FatalSessionError`. If it matches, the root is committed and the SYNC for the
  next part is returned, or, after the last part, queued blocks join the window.
- `retransmit()` returns the outstanding SYNC octet for octet. When the bounded count is
  exhausted the session ends (`SessionEnded`) and all state is discarded.

---

## Bidirectional sessions and scope (Sections 7, 10)

Each direction is its own chain with its own seq space from 0. An endpoint that both sends and
receives holds one `HctpSender` and one `HctpReceiver`; `ContextChain` bundles the two without
sharing state. The chain a SYNC belongs to is the direction it arrived on, never a block's
`role`. A transport that cannot tell the two directions apart carries only a one-way session.

An HCTP session is bound to one scope instance: one transport connection by default, or an
enclosing session defined by the carrying protocol. Create new objects when that instance ends
(or call `end()`), and never reset them while it continues. A fresh receiver cannot tell an
old first SYNC from a new one, so session freshness is the transport's job.

---

## Security notes (Section 11)

- The hashes are unkeyed. They detect corruption and out-of-context packets, not an attacker
  who can forge packets; authenticity and confidentiality come from the transport.
- No non-repudiation: either side can build a valid-looking chain from the genesis root.
- A summary can reveal what a turn said, and a content_hash lets anyone confirm a guessed
  plaintext. Encrypt the transport when that matters.
- Decompression is bounded by output size and block count, and dynamic_len is bounded before
  any read.

---

## Example

```python
from velamen import HctpSender, HctpReceiver

tx, rx = HctpSender(), HctpReceiver()
tx.add_turn("user", raw_text="...", summary="asked about X")

wire = tx.build_sync().serialize()        # send these octets over the transport
result = rx.receive(wire)                 # the peer runs the Section 6.3 checks
tx.receive_ack(result.ack_bytes)          # 38 octets back; roots now agree
assert tx.static_root == rx.local_root
```

## Test vectors

`tests/test_hctp01_vectors.py` runs the draft's Appendix A file (`vectors-01.json`, digest
pinned) and Konrad Gruszka's independent fold, encoding and packet vectors (MIT) from
`tests/vectors/`. See `tests/vectors/README.md` for where each file comes from.
