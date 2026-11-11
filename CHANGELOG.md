# Changelog

## 0.2.0 - 2026-11-11

HCTP now implements draft-ruvalcaba-hctp-01. The wire format (version 0x01) is unchanged, but
the canonical encoding and the receiver procedure changed, so this release does not
interoperate with 0.1.0 on non-ASCII context.

### Changed

- Canonical block encoding follows RFC 8785: non-ASCII is raw UTF-8, and only `"`, `\` and
  U+0000..U+001F are escaped. 0.1.0 wrote non-ASCII as `\uXXXX`, so any block with a non-ASCII
  role or summary now folds to a different root. ASCII-only roots are unchanged.
- dynamic_data carries the canonical block array, and a receiver accepts it only if the
  decompressed octets are exactly canonical: seq as plain ASCII digits, content_hash as 64
  lowercase hex digits, role 1 to 64 octets, summary at most 120 code points, exactly the four
  members, seqs contiguous, the last block's seq equal to the packet seq.
- The receiver applies the ordered checks of Section 6.3: framing, integrity, replay,
  duplicate (by SHA-256 of the received octets, answered with the cached ACK), alignment (the
  only fatal check), ingest validation, accept.
- zlib input must be exactly one complete stream with FDICT clear; decompression is bounded,
  and dynamic_len is bounded before it is read. A transport unit with octets after the packet
  is rejected.
- Sender and receiver state are separate classes (`HctpSender`, `HctpReceiver`).
  `ContextChain` bundles one of each for a bidirectional endpoint; each direction is its own
  chain with seq from 0.
- The sender freezes the window while a SYNC is outstanding, queues new blocks with their seq
  already assigned, splits a window above 64 blocks or 65536 octets into sequential parts,
  checks the ACK's new_root against its own fold (a mismatch ends the session), and
  retransmits octet for octet up to a bounded count.
- `ContextBlock.from_text` refuses a block that -01 makes invalid instead of truncating the
  summary.
- `ContextChain.acknowledge` takes the ACK (packet or octets), not a seq, because -01 checks
  its new_root. `ContextChain.ingest_sync` returns a `ReceiveResult` carrying the blocks and
  the ACK; `build_ack` is gone.

### Added

- `tests/test_hctp01_vectors.py`: the draft's Appendix A vectors and Konrad Gruszka's
  independent fold, encoding and packet vectors (MIT), vendored under `tests/vectors/`.

### Notes

- -01 removed the turn-token strategy from the draft. velamen never implemented it;
  per-direction chains are the only strategy.

## 0.1.0 - 2026-03-19

Initial release.
