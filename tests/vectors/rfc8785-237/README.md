# hctp-vectors-rfc8785-237

237 test vectors for draft-ruvalcaba-hctp-00, The Hash-Chain Context Transfer Protocol, as language-neutral JSON,
regenerated under the string rule agreed for -01: strings in canonical JSON follow RFC 8785, Section 3.2.2.2.

## The rule for strings

As agreed for -01, which has not been published yet. Only strings are concerned, not numbers; seq stays a plain
decimal integer (place 8).

- Characters outside ASCII are written as they are, in UTF-8. There is no Unicode normalization (place 10).
- Only the quotation mark, the reverse solidus and U+0000 to U+001F are escaped: \" and \\, then \b \t \n \f \r
  for U+0008, U+0009, U+000A, U+000C, U+000D, and \u00 followed by two lowercase hex digits for the other 27
  control characters.
- Nothing else is escaped. The solidus, U+007F, U+2028, U+2029, <, > and & are written as they are, and so is a
  character outside the BMP, as four UTF-8 bytes.
- A lone surrogate is not a valid string. There is no canonical form for it, and a receiver rejects it.
- Any other way of writing a string is not canonical, and a receiver rejects it (place 9).

## Changes since the package of 1 November 2026

The package of 1 November 2026 had 186 cases. This one keeps all of them under the same ids and adds 51.

- Same roots. Every root, canonical form, packet and outcome of the 186 earlier cases is unchanged, because the
  chosen readings at places 6 and 7 were already this rule. All 412 root values in those cases are the same. The
  one exception is the expected result of the four cases under "Following -01" below.
- Renamed. In encoding-01 to encoding-08 the columns ascii_escape and control_unicode_upper and their roots are now
  nonconforming_ascii_escape, nonconforming_control_unicode_upper, root_nonconforming_ascii_escape and
  root_nonconforming_control_unicode_upper, with the same values. Each encoding case also gives chosen_hex.
- Not conforming any more. place-06-alternative (non_ascii escape) and place-07-alternative (control
  unicode_upper) describe encodings that the rule excludes. Their variant is now nonconforming and valid_input is
  false; their roots are the same, and a conforming implementation must not produce them. place-06-chosen and
  place-07-chosen have the variant rule. The two nonconforming columns of 02_encoding.json are kept for comparison
  only.
- New, 43 encoding cases (encoding-09 to encoding-51), each with canonical bytes and the root after one fold:
  the 32 control characters one by one, the quotation mark, the reverse solidus, the solidus, U+007F, U+2028,
  U+2029, <, > and & raw, U+1D11E outside the BMP raw, and a lone surrogate as invalid input.
- New, 8 receiver cases (state-49 to state-56): seven SYNCs whose blocks are written in a
  non-conforming way (\u00fc, a surrogate pair escape, \u007f, \u000A, \u001F, \u000a instead of \n, \/), each
  rejected as not canonical, and one SYNC that carries every boundary of the rule written as the rule requires,
  accepted with its ACK.
- Following -01, Section 3.1. number-02 (1.0), number-03 (1e0) and number-04 (-0) give no seq value any more and
  valid_input is false: -01, lines 308-315, calls these spellings of seq not canonical, as the chosen reading at
  place 8 already did. Their RFC 8785 form (1, 1 and 0) is kept for comparison. place-38-alternative (content_hash
  in uppercase, case-insensitive comparison) has the variant nonconforming, valid_input false and the expected
  result mismatch: -01, lines 317-319, allows only 64 lowercase hexadecimal digits. Each of the four cases names
  those lines in draft_refs. place-38-alternative keeps case_insensitive true in its input: under -01 the form of
  content_hash is checked first, so a content_hash that is not canonical gives no match whatever the comparison.

## Where they come from

The vectors were produced by an independent implementation written from the text of draft-ruvalcaba-hctp-00
alone, without reading any other implementation. The implementation itself is not part of this package. For
every case, the decision (accepted, rejected, with which ACK) was written down by hand from the text; hashes,
roots and packet bytes were computed. Several values were recomputed without that implementation: the genesis
root, roots after one to four blocks, ACK bytes, a combined_hash and the decompressed payload of a SYNC. The
implementation also reproduces all 10 values of the first set of vectors Cristian shared.

All vectors refer to the text of draft-ruvalcaba-hctp-00.txt, 31087 octets, SHA-256
c9e80197104083f5ec86faf4beddf66b398bb6cd4f15cd7ccd45d841b17f7ad5. Section and line numbers are those of that
file, lines counted from 1. A reference that starts with draft-ruvalcaba-hctp-01 names the text of -01 that its author shared on
9 November 2026 before publication, 87115 octets, SHA-256
1dd7d6a4821b6284c66566b62901461dad259603599bdabb0769c0a0d5ee9e7b; its line numbers can move when -01 is published.

## Files

| File | Cases | Content |
|---|---|---|
| vectors/01_fold.json | 21 | Folding the rolling root (Section 4) over block sequences: empty, one, three, 1000 blocks, repetition, swapped order, one byte changed, insertion, deletion, non-ASCII, control characters, limits; six known wrong folds |
| vectors/02_encoding.json | 61 | Canonical JSON of one block under the rule, with RFC 8785 and two non-conforming encodings (ASCII-escaped, uppercase control escapes) for comparison, and the root after one fold for each; every boundary of the rule; ten number lexemes |
| vectors/03_packets.json | 22 | Decoding SYNC and ACK (Section 5): valid packets, empty and short input, unknown versions and packet types, wrong lengths, an oversized dynamic_len; two byte streams for self-delimiting (Section 10) |
| vectors/04_state_machine.json | 56 | Sender and receiver (Section 6) as scenarios: basic exchange, duplicate SYNC, lost ACK, retransmit limit, replay, integrity and alignment failures, full window, decompression limits, zlib and JSON ingest failures, non-conforming strings, ACK handling, seq limit; both strategies of Section 7 (two direction chains, turn-token) |
| vectors/05_summaries.json | 12 | Verifiable summaries (Section 8): raw text checks, an agreed test method, an equivalence predicate |
| vectors/06_readings.json | 65 | For places where the text allows two readings: a case under the chosen reading and the same case under the alternative reading, with outcomes that differ; for places 6 and 7 the rule and a non-conforming encoding; for place 38 an alternative that -01 makes non-conforming |
| | 237 | |

SHA256SUMS lists the SHA-256 of every file in this package except itself (`sha256sum -c SHA256SUMS`).

## Structure of a file

    {"file": "...", "description": "...", "cases": [ case, ... ]}

A case:

| Field | Meaning |
|---|---|
| id | unique across all files |
| kind | fold, fold_variant, encoding, number, packet, frames, scenario, summary |
| title | one sentence |
| draft_refs | sections and lines of -00 the case tests, and of -01 where a reference names it |
| valid_input | true: the input follows the text and must be accepted; false: a rejection, an error or a wrong form is expected |
| reading | optional: place (number), place_title, section_lines, variant (chosen, alternative, alternative_2; for places 6 and 7: rule, nonconforming; nonconforming for place-38-alternative) |
| note | optional: how an alternative was obtained, or why it is not executed |
| reading_switches | optional: the reading assumed instead of the chosen one (see below) |
| input | depends on kind |
| expected | the result under the chosen readings, or under reading_switches if present |

## Kinds

- fold: `blocks` (each with content_hash, role, seq, summary), or a `template` {role, summary, raw_text} with
  `count`, where "{i}" is replaced by the decimal seq and content_hash is SHA-256 of raw_text. Expected:
  canonical form and its SHA-256 per block and the roots root_0 to root_n (for up to 16 blocks), and `root`.
- fold_variant: a known wrong fold (`variant`); `equal` must be false.
- encoding: one `block`, or `block_json` (the block as JSON text, for input that is not valid). Expected: `chosen`
  (the canonical form under the rule), `chosen_hex` (its bytes), `rfc8785`, the two non-conforming encodings,
  `chosen_equals_rfc8785`, and the root after one fold for each; or `error` json_invalid for invalid input.
- number: a number `lexeme`, its RFC 8785 form and its value as seq (null if not an unsigned 32-bit integer, or if
  the lexeme is not the canonical spelling of seq: digits only, no sign, no leading zero, no fraction, no exponent).
- packet: `hex` of a packet; expected fields or `reason`.
- frames: `stream_hex`; packet lengths from the fixed fields (Section 10, self-delimiting).
- summary: a block, a raw text (or none), optionally the test method and the test predicate.
- scenario: `participants` (endpoints, `strategy` per_direction by default or turn_token, optional `token`,
  `start_seq`, `reading_switches`) and `steps`.

Scenario steps (`op`):

| op | parameters | result |
|---|---|---|
| add | who, role, summary, raw_text or content_hash | seq, or error |
| add_many | who, count, role, summary_template, raw_text_template ("{i}" = next seq) | last_seq, or error and after |
| send | who, as | packet (a view of the SYNC), or error |
| timeout | who, as | the retransmitted packet, or error |
| recv | who, packet (a name given with as) or hex | handled_by (receiver or sender), result, reason; ack and ack_hex when an ACK is sent; result packet_error with reason; result no_packet when the named packet was never produced |
| mutate | from, as, field (version, ptype, seq, static_root, new_root, dynamic_len, dynamic_data, combined_hash), offset, xor, rehash; or truncate, append | ok |
| build_sync | as, seq, static_root (hex, "genesis", "rx:X" or "tx:X" for an endpoint's current root), plain, plain_pattern {byte, count} or zlib_raw (hex), zlib_append, packet_append | informative |
| build_ack | as, seq, new_root | hex |
| state | who | the endpoint's sender state (tx) and receiver state (rx), and token |
| new_session | who | a fresh endpoint from genesis |
| compare | a, b | bytes_equal, dynamic_plain_equal, static_root_equal, seq_equal |

Results of recv: ack, ack_from_cache (an idempotent retransmission), discarded (silently, Section 6.3 step 1),
rejected (no ACK, session continues), fatal (session error, Section 6.6), accepted, ignored (an ACK at the
sender), packet_error.

A SYNC view: type, seq, static_root, dynamic_plain (if at most 2048 bytes), dynamic_plain_length,
dynamic_plain_sha256, integrity_ok, informative {dynamic_len, combined_hash, packet_sha256}.

## How to compare

- Compare everything except the fields under `informative`. Those depend on the zlib compressor: the vectors
  were produced with one compressor at level 6, and two compressors produce different bytes for the same blocks,
  so dynamic_len, combined_hash and the packet SHA-256 of a compressed SYNC differ between implementations.
- Where a SYNC is built from plain text (build_sync without zlib_raw), compress it yourself; the receiver's
  outcome must match.
- Reason codes (for example seq_gap, not_canonical) are names given by the producing implementation. Between
  implementations the decision is what counts: accepted with which ACK, discarded, rejected or fatal.
- Text in the data, such as "Rohtext A 0" (raw text) and "Zusammenfassung A 0" (summary), is opaque test data.
  It goes into hashes as it is. In scenarios, add for endpoint X and seq i uses the raw text "Rohtext X i" and
  the summary "Zusammenfassung X i".
- The test method test-whitespace-120/1 collapses runs of whitespace to one space, trims, and keeps the first
  120 code points. The test predicate "test" compares two summaries after collapsing whitespace and lowercasing.
  Neither is a recommendation.

## Readings rather than rules

The text leaves the following places open. Every case assumes the chosen reading at every place unless its
reading_switches or input explicitly select an alternative. Cases with a reading field identify the place
and the variant. The table contains 33 places, numbered 1 to 27 and 33 to 38. Numbers 1 to 27 follow the list
of open places sent to Cristian on 31 October 2026; numbers 28 to 32 of that list are further observations
without vectors here. Places 33 to 38 record additional implementation choices; their effects are shown by
the individual cases.

Places 6 and 7 are no longer open. For -01 they are the agreed rule for strings described above, and the table
gives that rule in their last column. Their earlier alternatives are kept as non-conforming encodings. The
alternative at place 38 (case-insensitive comparison of content_hash) is non-conforming under -01 as well, see
"Following -01" above.

| Place | Sections and lines of -00 | What is open | Chosen reading in these vectors |
|---|---|---|---|
| 1 | 5.1 lines 321-322, 346-348 | seq is not covered by combined_hash | the receiver rejects a SYNC whose seq differs from that of its last block |
| 2 | 6.1 line 416; 6.4 lines 488-489 | initial value of last_acked_seq | no value before the first ACK |
| 3 | 10 lines 610-622 against 6.3 lines 469-482 | splitting a window across SYNCs | parts one after another, each over the root after the previous ACK |
| 4 | 6.6 lines 531-532; 11 lines 650-654 against 4 lines 262-267 | "fresh genesis root" | every session starts at the one defined root_0 |
| 5 | 7 lines 548-552 against 6.5 lines 514-516 | turn-token and a lost ACK | literal: the original sender fails alignment |
| 6 | 3.1 lines 235-241 | characters outside ASCII (rule agreed for -01) | rule: raw UTF-8 with only the mandatory escapes (RFC 8785, Section 3.2.2.2) |
| 7 | 3.1 lines 235-241 | escapes for control characters (rule agreed for -01) | rule: \b \t \n \f \r, otherwise lowercase \u00xx |
| 8 | 3.1 lines 213-215, 235-241 | how seq is written | a plain decimal integer only |
| 9 | 3.1 lines 235-241; 5.1 lines 343-344; 6.3 lines 474-476 | receiver and non-canonical JSON | reject |
| 10 | 3.1 lines 217-219, 232-233, 235-241 | Unicode normalization | none |
| 11 | 3.1 lines 235-237 | extra, missing, duplicate members | reject |
| 12 | 3.1 lines 229-230 | form of content_hash at the receiver | exactly 64 lowercase hex digits, else reject |
| 13 | 3.1 lines 232-233; 9 line 597 | MAX_SUMMARY_LEN at the receiver | reject above 120 code points |
| 14 | 3.1 lines 217-219 | how short a "short" role is | no limit |
| 15 | 3.1 lines 213-215 | contiguous seq, checked | 0, 1, 2 without gaps, checked by the receiver |
| 16 | 3.1 lines 213-215 against 7 lines 536-546 | seq per session or per chain | from 0 in each direction chain |
| 17 | 5.1 lines 341-342 | ascending order in the array | reject out-of-order blocks |
| 18 | 5.1 lines 321-322; 6.2 line 429 | a SYNC without blocks | neither sent nor accepted |
| 19 | 5.1 lines 328, 350-352; 10 lines 606-607 | octets after combined_hash | packet must be exactly 74 + dynamic_len octets |
| 20 | 5.1 line 330; 9 line 601 | details of the zlib stream | one complete stream, no preset dictionary, nothing after its end |
| 21 | 6.3 lines 439-440, 459-467 | replay rule before integrity | checks in the stated order |
| 22 | 6.3 lines 453-463 | same seq, different root | falls through to checks 3 to 5 |
| 23 | 5.1 lines 316-317; 6.3 lines 465-472; 6.6 lines 522-525 | what "reject" means | no ACK, session continues; only a root mismatch is fatal |
| 24 | 6.4 lines 491-498 against 5.1 lines 321-322 | which blocks the sender folds on ACK | only the blocks carried by the acknowledged SYNC |
| 25 | 6.4 lines 491-495; 6.6 lines 522-525 | ACK with a wrong new_root | fatal, tentative fold only |
| 26 | 6.5 lines 517-518; 6.3 lines 478-482 | state after transport failure | report and keep state |
| 27 | 11 lines 656-661 | values of the limits | dynamic_len and decompressed size 1 MiB each, 1024 blocks per SYNC, limits inclusive |
| 33 | 5.1 line 330, 346-348; 9 line 601 | compression level not fixed | any level; these vectors use level 6 |
| 34 | 6.1 line 418; 6.5 lines 511-518 | retransmit timer and limit | at most 3 retransmissions, byte-identical |
| 35 | 6.6 lines 529-532 | "approaching 2^32" | seq 4294967295 is the last assignable |
| 36 | 7 lines 543-545 | direction from role or channel | from the channel and the packet type |
| 37 | 7 lines 548-552 | turn-token start and hand-over | holder set at the start; the token passes to the endpoint that sends an ACK; one shared root and seq counter |
| 38 | 8 lines 567-571 | checking the raw text | SHA-256 over the UTF-8 bytes, no normalization, exact comparison |

## reading_switches

The switches name the reading assumed instead of the chosen one. Their defaults are the chosen readings.

| Switch | Default | Alternative values in the vectors | Place |
|---|---|---|---|
| check_seq_is_last | true | false | 1, 22 |
| last_acked_initial_zero | false | true | 2 |
| non_ascii | raw | escape (everything outside U+0020..U+007E as \uXXXX, lowercase, surrogate pairs); not conforming to the rule for -01, a receiver rejects it (place 9) | 6 |
| control | short | unicode_upper; not conforming to the rule for -01, a receiver rejects it (place 9) | 7 |
| canon_mode | strict | recanonicalize, raw_bytes | 8, 9, 11 |
| reject_extra_members | true | false | 11 |
| duplicate_members | reject | last_wins | 11 |
| check_content_hash_form | true | false | 12 |
| enforce_summary_len | true | false | 13 |
| max_role_len | none | 32 | 14 |
| check_contiguous | true | false | 15, 17 |
| seq_scope | per_chain | per_session | 16 |
| check_ascending | true | false | 17 |
| allow_empty_sync | false | true | 18, 37 |
| allow_trailing_packet | false | true | 19 |
| allow_trailing_zlib | false | true | 20 |
| integrity_first | false | true | 21 |
| equal_seq_other_root | fall_through | discard | 22 |
| integrity_fatal | false | true | 23 |
| ack_mismatch | fatal | ignore_tentative, ignore_folded_in | 25 |
| max_blocks | 1024 | 1023 | 27 |
| level | 6 | 0, 9 (per participant) | 33 |
| max_retransmits | 3 | 1 | 34 |
| last_usable_seq | 4294967295 | 4294967294 | 35 |
| max_blocks_per_send | 1024 | 1025 (per participant) | full-window cases |

Further fixed values, where the text names none: dynamic_len and decompressed size are limited to 1 MiB each.

## License

MIT, see LICENSE.
