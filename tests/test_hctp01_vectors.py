# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""draft-ruvalcaba-hctp-01 conformance against published test vectors.

Two vector sets, both vendored under tests/vectors/ (see the README there):

- hctp-01/vectors-01.json: the file whose SHA-256 Appendix A of the draft prints.
- rfc8785-237/: Konrad Gruszka's independent vectors (MIT), fold, encoding and
  packet cases, copied from saluca-labs/hctp at a pinned commit.

Each file's digest is pinned here, so a changed copy fails rather than passing on
different data.
"""

import hashlib
import json
import re
import zlib
from pathlib import Path

import pytest

from velamen import hctp

VEC = Path(__file__).parent / "vectors"
VECTORS_01 = VEC / "hctp-01" / "vectors-01.json"
VECTORS_01_SHA256 = "c452fd2400f8dfd74d3d3b4c9fc8c217e5528017366fa50cd358391a31d17b99"
K237 = VEC / "rfc8785-237"
GENESIS = hashlib.sha256(b"hctp-genesis-v1").digest()


def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


# --------------------------------------------------------------------------
# Integrity of the vendored files
# --------------------------------------------------------------------------

def test_vectors_01_digest_matches_appendix_a():
    assert hashlib.sha256(VECTORS_01.read_bytes()).hexdigest() == VECTORS_01_SHA256


def test_konrad_files_match_their_sha256sums():
    sums = {}
    for line in (K237 / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*")] = digest
    vendored = ["LICENSE", "README.md", "vectors/01_fold.json", "vectors/02_encoding.json",
                "vectors/03_packets.json"]
    for name in vendored:
        assert hashlib.sha256((K237 / name).read_bytes()).hexdigest() == sums[name], name


# --------------------------------------------------------------------------
# vectors-01.json (Appendix A)
# --------------------------------------------------------------------------

V01 = _load(VECTORS_01)


def test_genesis_root():
    assert hctp.genesis_root().hex() == V01["genesis_root"]


@pytest.mark.parametrize("name", sorted(V01["sequences"]))
def test_vectors_01_sequence(name):
    seq = V01["sequences"][name]
    root = hctp.genesis_root()
    for inp, want in zip(seq["blocks"], seq["folds"], strict=True):
        block = hctp.ContextBlock.from_text(inp["seq"], inp["role"], inp["raw_text"], inp["summary"])
        assert block.content_hash == inp["content_hash"]
        assert block.canonical_bytes().hex() == want["canonical_hex"]
        assert _sha(block.canonical_bytes()).hex() == want["block_hash"]
        root = hctp.fold(root, block)
        assert root.hex() == want["root"]


def test_vectors_01_sync_and_ack_receiver():
    """A receiver accepts the Appendix A.4 SYNC octets and answers with exactly its ACK."""
    ex = V01["packet_example"]
    rx = hctp.HctpReceiver()
    result = rx.receive(bytes.fromhex(ex["sync_hex"]))
    assert result.outcome == "accepted"
    assert result.ack_bytes.hex() == ex["ack_hex"]
    assert zlib.decompress(bytes.fromhex(ex["dynamic_data_hex"])).decode() == ex["uncompressed_array"]


def test_vectors_01_sync_and_ack_sender():
    """A sender of the ascii-3 blocks emits the A.4 array and accepts the A.4 ACK."""
    ex = V01["packet_example"]
    tx = hctp.HctpSender()
    for b in V01["sequences"]["ascii-3"]["blocks"]:
        tx.add_turn(b["role"], b["raw_text"], b["summary"])
    sync = tx.build_sync()
    assert sync.static_root == GENESIS
    assert zlib.decompress(sync.dynamic_data).decode("utf-8") == ex["uncompressed_array"]
    assert tx.receive_ack(bytes.fromhex(ex["ack_hex"])) is None
    assert tx.static_root.hex() == V01["sequences"]["ascii-3"]["folds"][-1]["root"]


def _sync_for(decompressed: bytes, seq: int) -> bytes:
    dyn = zlib.compress(decompressed, 9)
    return hctp.SyncPacket(seq=seq, static_root=GENESIS, dynamic_data=dyn,
                           combined_hash=_sha(GENESIS + dyn)).serialize()


def _packet_seq(text: str) -> int:
    """The seq a sender would put in P.seq: that of the last block, else 0."""
    found = re.findall(r'"seq":(\d+)[,}]', text)
    return int(found[-1]) if found else 0


def test_must_reject_positive_control():
    """The wrapper used below is accepted for a canonical array, so a rejection means something."""
    blocks = V01["sequences"]["ascii-3"]["folds"]
    arr = "[" + ",".join(f["canonical"] for f in blocks) + "]"
    assert hctp.HctpReceiver().receive(_sync_for(arr.encode(), 2)).outcome == "accepted"


@pytest.mark.parametrize("case", V01["must_reject"], ids=lambda c: c["reason"])
def test_vectors_01_must_reject(case):
    rx = hctp.HctpReceiver()
    text = case["decompressed"]
    with pytest.raises(hctp.Rejected) as info:
        rx.receive(_sync_for(text.encode("utf-8"), _packet_seq(text)))
    assert info.value.step == "ingest"
    assert rx.has_seen is False and rx.local_root == GENESIS and rx.ack_cache is None


# --------------------------------------------------------------------------
# Konrad Gruszka's rfc8785-237 set: fold, fold_variant, encoding, packet
# --------------------------------------------------------------------------

def _cases(name: str, kinds: tuple[str, ...]) -> list[dict]:
    return [c for c in _load(K237 / "vectors" / name)["cases"] if c["kind"] in kinds]


FOLD_CASES = _cases("01_fold.json", ("fold", "fold_variant"))
ENCODING_CASES = _cases("02_encoding.json", ("encoding",))
PACKET_CASES = _cases("03_packets.json", ("packet",))


def _expand(inp: dict) -> list[dict]:
    if "blocks" in inp:
        return inp["blocks"]
    t, out = inp["template"], []
    for i in range(inp["count"]):
        raw = t["raw_text"].replace("{i}", str(i))
        out.append({"seq": i, "role": t["role"].replace("{i}", str(i)),
                    "summary": t["summary"].replace("{i}", str(i)),
                    "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
    return out


def _fold_all(blocks: list[dict]):
    root, roots, canon = GENESIS, [GENESIS.hex()], []
    for d in blocks:
        b = hctp.ContextBlock.from_dict(d)
        canon.append(b.canonical_bytes())
        root = hctp.fold(root, b)
        roots.append(root.hex())
    return root.hex(), roots, canon


def test_konrad_case_counts():
    """79 fold and encoding cases, 20 packet cases: a short read would fail here."""
    assert (len(FOLD_CASES), len(ENCODING_CASES), len(PACKET_CASES)) == (21, 51, 20)


@pytest.mark.parametrize("case", FOLD_CASES, ids=lambda c: c["id"])
def test_konrad_fold(case):
    exp = case["expected"]
    root, roots, canon = _fold_all(_expand(case["input"]))
    if case["kind"] == "fold_variant":
        if exp.get("root_correct") is not None:
            assert root == exp["root_correct"]
    elif case.get("valid_input") is False:
        # a non-conforming reading: a conforming encoder must NOT reproduce its root
        assert root != exp["root"]
    else:
        assert root == exp["root"]
        if "canonical" in exp:
            got = [c.decode("utf-8") for c in canon[:len(exp["canonical"])]]
            assert got == exp["canonical"]
        if "roots" in exp:
            assert roots[:len(exp["roots"])] == exp["roots"]


@pytest.mark.parametrize("case", ENCODING_CASES, ids=lambda c: c["id"])
def test_konrad_encoding(case):
    exp, inp = case["expected"], case["input"]
    if "block_json" in inp or exp.get("error"):
        with pytest.raises((hctp.InvalidBlock, ValueError)):
            blk = json.loads(inp["block_json"]) if "block_json" in inp else inp["block"]
            hctp.ContextBlock.from_dict(blk).canonical_bytes()
        return
    got = hctp.ContextBlock.from_dict(inp["block"]).canonical_bytes()
    assert got.hex() == exp["chosen_hex"]
    key = next((k for k in ("root_chosen", "root") if k in exp), None)
    if key:
        assert _sha(GENESIS + _sha(got)).hex() == exp[key]


@pytest.mark.parametrize("case", PACKET_CASES, ids=lambda c: c["id"])
def test_konrad_packet(case):
    exp = case["expected"]
    data = bytes.fromhex(case["input"]["hex"])
    assert len(data) == exp.get("length", len(data))
    if exp["type"] == "error":
        with pytest.raises(hctp.PacketError) as info:
            hctp.parse_packet(data)
        assert info.value.reason == exp["reason"]
        return
    pkt = hctp.parse_packet(data)
    if exp["type"] == "ack":
        assert isinstance(pkt, hctp.AckPacket)
        assert (pkt.seq, pkt.new_root.hex()) == (exp["seq"], exp["new_root"])
        return
    assert isinstance(pkt, hctp.SyncPacket) and pkt.verify()
    assert (pkt.seq, pkt.static_root.hex()) == (exp["seq"], exp["static_root"])
    plain = zlib.decompress(pkt.dynamic_data)
    assert plain.decode("utf-8") == exp["dynamic_plain"]
    blocks = pkt.decode_blocks()
    assert blocks[-1].seq == exp["seq"]


# --------------------------------------------------------------------------
# Konrad Gruszka's number lexemes (02_encoding.json, kind "number") against the
# seq rule of -01 Section 3.1: ASCII digits only, no sign, no leading zero except
# for 0, no fraction, no exponent, value 0..4294967295.
# --------------------------------------------------------------------------

NUMBER_CASES = _cases("02_encoding.json", ("number",))
_NUMBER_HASH = hashlib.sha256(b"number").hexdigest()


def _array_with_seq(lexeme: str) -> bytes:
    """A one-block array, canonical in every member, whose seq is written as `lexeme`."""
    return ('[{"content_hash":"%s","role":"user","seq":%s,"summary":"n"}]'
            % (_NUMBER_HASH, lexeme)).encode("ascii")


def test_konrad_number_case_count():
    assert len(NUMBER_CASES) == 10
    assert sum(c["valid_input"] for c in NUMBER_CASES) == 2


@pytest.mark.parametrize("case", NUMBER_CASES, ids=lambda c: c["id"])
def test_konrad_number_as_seq(case):
    lexeme, exp = case["input"]["lexeme"], case["expected"]
    raw = _array_with_seq(lexeme)
    if case["valid_input"]:
        (block,) = hctp.parse_block_array(raw)
        assert type(block.seq) is int and block.seq == exp["seq_value"]
        # the encoder writes this seq back as the RFC 8785 form he gives
        assert block.canonical_bytes() == _array_with_seq(exp["rfc8785"])[1:-1]
    else:
        assert exp["seq_value"] is None
        with pytest.raises(hctp.InvalidBlock):
            hctp.parse_block_array(raw)
