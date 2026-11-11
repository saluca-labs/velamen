# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""Behaviour of the HCTP layer under draft-ruvalcaba-hctp-01 (Sections 5, 6, 7)."""

import hashlib
import struct
import zlib

import pytest

from velamen.hctp import (
    AckPacket, ContextBlock, ContextChain, FatalSessionError, HctpReceiver, HctpSender,
    MAX_BLOCKS_PER_SYNC_BASE, Rejected, SessionEnded, SyncPacket, genesis_root,
)


def _exchange(tx: HctpSender, rx: HctpReceiver):
    sync = tx.build_sync()
    result = rx.receive(sync.serialize())
    tx.receive_ack(result.ack_bytes)
    return sync, result


def _sync(static_root: bytes, raw: bytes, seq: int, dyn: bytes = None) -> bytes:
    dyn = zlib.compress(raw, 9) if dyn is None else dyn
    return SyncPacket(seq, static_root, dyn, hashlib.sha256(static_root + dyn).digest()).serialize()


def test_roundtrip_sync_ack():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "Hello", "greeting")
    tx.add_turn("agent", "Hi there", "response")
    sync, result = _exchange(tx, rx)
    assert result.outcome == "accepted"
    assert [b.summary for b in result.blocks] == ["greeting", "response"]
    assert sync.seq == 1 and result.ack.seq == 1
    assert tx.static_root == rx.local_root == result.ack.new_root
    assert tx.last_acked_seq == 1 and tx.pending_seq is None and tx.dynamic == []


def test_packet_serialization():
    tx = HctpSender()
    tx.add_turn("user", "test message", "test")
    packet = tx.build_sync()
    wire = packet.serialize()
    assert len(wire) == 74 + len(packet.dynamic_data)
    restored = SyncPacket.deserialize(wire)
    assert restored == packet and restored.verify()
    ack = AckPacket(seq=0, new_root=b"\x01" * 32)
    assert AckPacket.deserialize(ack.serialize()) == ack and len(ack.serialize()) == 38


def test_tamper_detection_is_silent_and_non_fatal():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "secret", "secret msg")
    wire = bytearray(tx.build_sync().serialize())
    wire[42] ^= 0xFF
    with pytest.raises(Rejected) as info:
        rx.receive(bytes(wire))
    assert info.value.step == "integrity"
    assert rx.receive(tx.retransmit()).outcome == "accepted"


def test_static_root_does_not_advance_at_send_time():
    tx = HctpSender()
    tx.add_turn("user", "a", "a")
    tx.build_sync()
    assert tx.static_root == genesis_root()


def test_lost_ack_retransmission_gets_cached_ack_without_refold():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "first", "first msg")
    first = rx.receive(tx.build_sync().serialize())     # ACK lost in transit
    root_after = rx.local_root
    again = rx.receive(tx.retransmit())
    assert again.outcome == "duplicate"
    assert again.ack_bytes == first.ack_bytes
    assert rx.local_root == root_after
    tx.receive_ack(again.ack_bytes)
    assert tx.static_root == rx.local_root


def test_same_seq_different_octets_is_discarded():
    """An injected SYNC with the cached seq and a consistent combined_hash gets silence."""
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "first", "first msg")
    rx.receive(tx.build_sync().serialize())
    forged = ContextBlock.from_text(0, "user", "forged", "forged")
    raw = b"[" + forged.canonical_bytes() + b"]"
    with pytest.raises(Rejected) as info:
        rx.receive(_sync(genesis_root(), raw, 0))
    assert info.value.step == "duplicate"


def test_replay_of_superseded_sync_is_discarded():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "one", "one")
    old, _ = _exchange(tx, rx)
    tx.add_turn("user", "two", "two")
    _exchange(tx, rx)
    with pytest.raises(Rejected) as info:
        rx.receive(old.serialize())
    assert info.value.step == "replay"


def test_alignment_mismatch_is_fatal():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "one", "one")
    _exchange(tx, rx)
    other = HctpSender()                     # a sender still at the genesis root
    other.add_turn("user", "x", "x")
    other.add_turn("user", "y", "y")
    with pytest.raises(FatalSessionError):
        rx.receive(other.build_sync().serialize())
    with pytest.raises(SessionEnded):
        rx.receive(other.retransmit())


def test_ack_with_wrong_root_is_fatal_for_sender():
    tx = HctpSender()
    tx.add_turn("user", "one", "one")
    sync = tx.build_sync()
    with pytest.raises(FatalSessionError):
        tx.receive_ack(AckPacket(seq=sync.seq, new_root=b"\x00" * 32))
    assert tx.ended and tx.static_root == genesis_root()


def test_first_ack_for_seq_zero_is_processed():
    """last_acked_seq is undefined, not -1 or 0, so the ACK for a SYNC carrying only block 0 counts."""
    tx, rx = HctpSender(), HctpReceiver()
    assert tx.last_acked_seq is None
    tx.add_turn("user", "zero", "zero")
    _exchange(tx, rx)
    assert tx.last_acked_seq == 0


def test_stale_ack_is_discarded_without_state_change():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "zero", "zero")
    _, first = _exchange(tx, rx)
    tx.add_turn("user", "one", "one")
    tx.build_sync()
    with pytest.raises(Rejected):
        tx.receive_ack(first.ack_bytes)
    assert tx.pending_seq == 1


def test_blocks_originated_while_frozen_are_queued_with_their_seq():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "zero", "zero")
    sync = tx.build_sync()
    late = tx.add_turn("user", "one", "one")
    assert late.seq == 1 and tx.queue == [late] and len(tx.dynamic) == 1
    tx.receive_ack(rx.receive(sync.serialize()).ack_bytes)
    assert tx.dynamic == [late] and tx.queue == []
    _exchange(tx, rx)
    assert rx.last_block_seq == 1


def test_window_over_baseline_is_sent_in_sequential_parts():
    tx, rx = HctpSender(), HctpReceiver()
    n = MAX_BLOCKS_PER_SYNC_BASE + 6
    for i in range(n):
        tx.add_turn("user", f"t{i}", f"s{i}")
    sync = tx.build_sync()
    assert sync.seq == MAX_BLOCKS_PER_SYNC_BASE - 1
    tx.add_turn("user", "late", "late")        # queued until the last part is ACKed
    nxt = tx.receive_ack(rx.receive(sync.serialize()).ack_bytes)
    assert nxt is not None and nxt.seq == n - 1 and nxt.static_root == rx.local_root
    assert tx.receive_ack(rx.receive(nxt.serialize()).ack_bytes) is None
    assert tx.static_root == rx.local_root and rx.last_block_seq == n - 1
    assert [b.seq for b in tx.dynamic] == [n]


def test_retransmit_exhaustion_ends_session():
    tx = HctpSender(max_retransmits=2)
    tx.add_turn("user", "zero", "zero")
    wire = tx.build_sync().serialize()
    assert tx.retransmit() == wire and tx.retransmit() == wire
    with pytest.raises(SessionEnded):
        tx.retransmit()
    assert tx.ended and tx.dynamic == [] and tx.pending_seq is None


def test_trailing_octets_after_packet_fail_framing():
    tx, rx = HctpSender(), HctpReceiver()
    tx.add_turn("user", "zero", "zero")
    with pytest.raises(Rejected) as info:
        rx.receive(tx.build_sync().serialize() + b"\x00")
    assert info.value.step == "framing"


@pytest.mark.parametrize("mutate", ["trailing", "truncated", "two_streams", "fdict"])
def test_zlib_stream_must_be_exactly_one_complete_stream(mutate):
    block = ContextBlock.from_text(0, "user", "raw", "s")
    raw = b"[" + block.canonical_bytes() + b"]"
    dyn = zlib.compress(raw, 9)
    dyn = {"trailing": dyn + b"\x00", "truncated": dyn[:-3], "two_streams": dyn + dyn,
           "fdict": bytes([dyn[0], dyn[1] | 0x20]) + dyn[2:]}[mutate]
    rx = HctpReceiver()
    with pytest.raises(Rejected) as info:
        rx.receive(_sync(genesis_root(), raw, 0, dyn))
    assert info.value.step == "ingest" and not rx.has_seen


def test_packet_seq_must_equal_last_block_seq():
    """K1: an inflated P.seq is rejected, so it cannot make a real retransmission look like a replay."""
    block = ContextBlock.from_text(0, "user", "raw", "s")
    rx = HctpReceiver()
    with pytest.raises(Rejected):
        rx.receive(_sync(genesis_root(), b"[" + block.canonical_bytes() + b"]", 7))


def test_dynamic_len_above_bound_rejected_before_read():
    head = struct.pack(">BBI", 1, 0x53, 0) + genesis_root() + struct.pack(">I", 0xFFFFFFFF)
    with pytest.raises(Rejected) as info:
        HctpReceiver().receive(head + b"\x00" * 32)
    assert info.value.step == "framing"


def test_bidirectional_chains_are_independent():
    alice, bob = ContextChain(), ContextChain()
    alice.add_turn("agent", "a0", "a0")         # role is a label, not a chain selector
    bob.add_turn("user", "b0", "b0")
    a_sync, b_sync = alice.build_sync_packet(), bob.build_sync_packet()
    assert a_sync.seq == b_sync.seq == 0         # each chain numbers from 0
    alice.acknowledge(bob.ingest_sync(a_sync).ack)
    bob.acknowledge(alice.ingest_sync(b_sync).ack)
    assert alice.sender.static_root == bob.receiver.local_root
    assert bob.sender.static_root == alice.receiver.local_root
    assert alice.sender.static_root != bob.sender.static_root


def test_acknowledge_requires_the_ack_not_a_seq():
    chain = ContextChain()
    chain.add_turn("user", "x", "x")
    chain.build_sync_packet()
    with pytest.raises(TypeError):
        chain.acknowledge(0)


def test_context_block_from_text():
    block = ContextBlock.from_text(0, "user", "hello world", "greeting")
    assert block.content_hash == hashlib.sha256(b"hello world").hexdigest()
    assert block.summary == "greeting"


@pytest.mark.parametrize("role,summary", [("", "s"), ("r" * 65, "s"), ("user", "s" * 121)])
def test_from_text_refuses_invalid_block(role, summary):
    with pytest.raises(ValueError):
        ContextBlock.from_text(0, role, "raw", summary)


def test_summary_limit_counts_code_points():
    block = ContextBlock.from_text(0, "user", "raw", "\U0001F600" + "x" * 119)
    assert len(block.summary) == 120
