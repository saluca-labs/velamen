# HCTP test vectors

Read by `tests/test_hctp01_vectors.py`. Every file is pinned by its SHA-256 in that test, so
an altered copy fails instead of passing on different data. `.gitattributes` marks this
directory `-text` so line endings are never rewritten.

## hctp-01/vectors-01.json

The test vectors of draft-ruvalcaba-hctp-01 (Saluca LLC), generated from the draft text by
the author's vector generator. Appendix A of the draft prints this file's SHA-256:

    c452fd2400f8dfd74d3d3b4c9fc8c217e5528017366fa50cd358391a31d17b99

It holds seven fold sequences (ASCII, non-ASCII, the escaped set, characters that must not be
escaped, a non-BMP character, NFC and NFD forms, a summary of exactly 120 code points), the
Appendix A.4 SYNC and ACK, and 21 decompressed SYNC contents a receiver must reject.

## rfc8785-237/

Konrad Gruszka's independent HCTP vectors under the RFC 8785 string rule, MIT licensed
(`rfc8785-237/LICENSE`, kept with the files as the licence requires). Copied unmodified from
[saluca-labs/hctp](https://github.com/saluca-labs/hctp) at commit
`6a2c9a4e0952d969a8d026ea931158ff2ab34b74`, path `test-vectors/rfc8785-237/`.

Only part of the package is copied: `LICENSE`, `README.md`, `SHA256SUMS`,
`vectors/01_fold.json`, `vectors/02_encoding.json` and `vectors/03_packets.json`. The test
checks each copied file against `SHA256SUMS`. The other three files (state-machine scenarios,
summaries, alternative readings) are in the source repository.

His vectors were written against draft-ruvalcaba-hctp-00 with the string rule that -01
adopted. One fold case (`fold-15`) uses an empty role, which -01 makes an invalid block: velamen
still encodes and folds it to his root, because the encoding is defined, but `from_text` and a
receiver refuse such a block.

`02_encoding.json` also holds his ten number lexemes (kind `number`). They run as the seq of
an otherwise canonical block through `parse_block_array`: `1` and `4294967295` parse to their
value, and the eight his file marks `valid_input: false` are refused, including `1.0`, `1e0`
and `-0`, which -01 Section 3.1 makes non-canonical spellings of seq.
