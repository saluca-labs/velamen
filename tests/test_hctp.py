# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""Tests for the HCTP protocol layer."""

from velamen.hctp import ContextChain, SyncPacket, AckPacket, ContextBlock


def test_roundtrip_sync_ack():
    """Sender builds SYNC, receiver ingests + ACKs, sender acknowledges."""
    sender = ContextChain()
    sender.add_turn("user", "Hello", "greeting")
    sender.add_turn("agent", "Hi there", "response")

    packet = sender.build_sync_packet()
    wire = packet.serialize()

    # Receiver
    receiver = ContextChain()
    blocks = receiver.ingest_sync(packet)
    assert len(blocks) == 2
    assert blocks[0].role == "user"
    assert blocks[1].summary == "response"

    ack = receiver.build_ack(packet)
    ack_wire = ack.serialize()

    # Sender processes ACK
    new_root = sender.acknowledge(ack.seq)
    assert new_root == ack.new_root


def test_packet_serialization():
    """SyncPacket and AckPacket survive serialize/deserialize."""
    chain = ContextChain()
    chain.add_turn("user", "test message", "test")
    packet = chain.build_sync_packet()

    wire = packet.serialize()
    restored = SyncPacket.deserialize(wire)

    assert restored.seq == packet.seq
    assert restored.static_root == packet.static_root
    assert restored.combined_hash == packet.combined_hash
    assert restored.verify()


def test_tamper_detection():
    """Modified dynamic data breaks verification."""
    chain = ContextChain()
    chain.add_turn("user", "secret", "secret msg")
    packet = chain.build_sync_packet()

    # Tamper with dynamic data
    tampered = bytearray(packet.dynamic_data)
    if len(tampered) > 0:
        tampered[0] ^= 0xFF
    packet.dynamic_data = bytes(tampered)

    assert not packet.verify()


def test_replay_rejection():
    """Receiver rejects replayed SYNC packets."""
    sender = ContextChain()
    receiver = ContextChain()

    sender.add_turn("user", "first", "first msg")
    pkt1 = sender.build_sync_packet()
    receiver.ingest_sync(pkt1)
    receiver.build_ack(pkt1)

    # Replay same packet
    try:
        receiver.ingest_sync(pkt1)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Replay" in str(e) or "last_acked_seq" in str(e)


def test_multi_round():
    """Multiple sync rounds maintain chain integrity."""
    sender = ContextChain()
    receiver = ContextChain()

    # Round 1
    sender.add_turn("user", "hello", "greeting")
    pkt = sender.build_sync_packet()
    receiver.ingest_sync(pkt)
    ack = receiver.build_ack(pkt)
    sender.acknowledge(ack.seq)

    # Round 2
    sender.add_turn("agent", "world", "reply")
    pkt2 = sender.build_sync_packet()
    receiver.ingest_sync(pkt2)
    ack2 = receiver.build_ack(pkt2)
    new_root = sender.acknowledge(ack2.seq)

    assert new_root == ack2.new_root
    assert sender.static_root == receiver.static_root


def test_context_block_from_text():
    """ContextBlock.from_text produces valid hash."""
    import hashlib
    block = ContextBlock.from_text(0, "user", "hello world", "greeting")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert block.content_hash == expected
    assert block.summary == "greeting"
