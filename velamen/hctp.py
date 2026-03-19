# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
HCTP -- Hash-Chain Context Transfer Protocol
=============================================
Protocol layer for transferring conversational context as a compact,
tamper-evident, hash-chained payload. Only the delta (dynamic section)
crosses the wire; the full history is represented as a 32-byte static
root hash.

See docs/PROTOCOL.md for full spec.
"""

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

PROTO_VERSION = 0x01
PTYPE_SYNC = 0x53   # 'S'
PTYPE_ACK = 0x41    # 'A'
GENESIS_SEED = b"hctp-genesis-v1"
MAX_SUMMARY_LEN = 120


@dataclass
class ContextBlock:
    """A single conversation turn."""
    seq: int
    role: str
    content_hash: str
    summary: str

    @staticmethod
    def from_text(seq: int, role: str, raw_text: str, summary: str) -> "ContextBlock":
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        summary = summary[:MAX_SUMMARY_LEN]
        return ContextBlock(seq=seq, role=role,
                            content_hash=content_hash, summary=summary)

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "role": self.role,
            "content_hash": self.content_hash,
            "summary": self.summary,
        }

    @staticmethod
    def from_dict(d: dict) -> "ContextBlock":
        return ContextBlock(
            seq=d["seq"], role=d["role"],
            content_hash=d["content_hash"], summary=d["summary"],
        )

    def canonical_bytes(self) -> bytes:
        """Stable serialization used in hash chain."""
        return json.dumps(self.to_dict(), separators=(",", ":"),
                          sort_keys=True).encode("utf-8")


@dataclass
class SyncPacket:
    """SYNC wire packet. Carries static root + compressed dynamic delta."""
    seq: int
    static_root: bytes
    dynamic_data: bytes
    combined_hash: bytes

    def serialize(self) -> bytes:
        dyn_len = len(self.dynamic_data)
        return (
            struct.pack(">BB", PROTO_VERSION, PTYPE_SYNC)
            + struct.pack(">I", self.seq)
            + self.static_root
            + struct.pack(">I", dyn_len)
            + self.dynamic_data
            + self.combined_hash
        )

    @staticmethod
    def deserialize(data: bytes) -> "SyncPacket":
        if len(data) < 74:
            raise ValueError(f"Packet too short: {len(data)} bytes")
        ver, ptype = struct.unpack_from(">BB", data, 0)
        if ver != PROTO_VERSION:
            raise ValueError(f"Unknown protocol version: {ver}")
        if ptype != PTYPE_SYNC:
            raise ValueError(f"Expected SYNC packet (0x53), got 0x{ptype:02x}")
        seq, = struct.unpack_from(">I", data, 2)
        static_root = data[6:38]
        dyn_len, = struct.unpack_from(">I", data, 38)
        dynamic_data = data[42: 42 + dyn_len]
        combined_hash = data[42 + dyn_len: 42 + dyn_len + 32]
        return SyncPacket(seq=seq, static_root=static_root,
                          dynamic_data=dynamic_data, combined_hash=combined_hash)

    def verify(self) -> bool:
        """Recompute combined_hash and confirm integrity."""
        expected = hashlib.sha256(self.static_root + self.dynamic_data).digest()
        return expected == self.combined_hash

    def decode_blocks(self) -> list[ContextBlock]:
        raw = zlib.decompress(self.dynamic_data)
        dicts = json.loads(raw.decode("utf-8"))
        return [ContextBlock.from_dict(d) for d in dicts]


@dataclass
class AckPacket:
    """ACK wire packet. Echoes seq + sends updated static root."""
    seq: int
    new_root: bytes

    def serialize(self) -> bytes:
        return (
            struct.pack(">BB", PROTO_VERSION, PTYPE_ACK)
            + struct.pack(">I", self.seq)
            + self.new_root
        )

    @staticmethod
    def deserialize(data: bytes) -> "AckPacket":
        if len(data) < 38:
            raise ValueError(f"ACK too short: {len(data)} bytes")
        ver, ptype = struct.unpack_from(">BB", data, 0)
        if ptype != PTYPE_ACK:
            raise ValueError(f"Expected ACK (0x41), got 0x{ptype:02x}")
        seq, = struct.unpack_from(">I", data, 2)
        new_root = data[6:38]
        return AckPacket(seq=seq, new_root=new_root)


def _genesis_root() -> bytes:
    return hashlib.sha256(GENESIS_SEED).digest()


def _fold_block(root: bytes, block: ContextBlock) -> bytes:
    """Advance the static root by folding in one block."""
    block_hash = hashlib.sha256(block.canonical_bytes()).digest()
    return hashlib.sha256(root + block_hash).digest()


def _compress_blocks(blocks: list[ContextBlock]) -> bytes:
    dicts = [b.to_dict() for b in blocks]
    raw = json.dumps(dicts, separators=(",", ":")).encode("utf-8")
    return zlib.compress(raw, level=9)


class ContextChain:
    """
    Manages a hash-chained conversation context.

    - static_root: hash of all acknowledged history
    - dynamic:     pending turns not yet acknowledged
    - _seq:        next block sequence number
    """

    def __init__(self, static_root: Optional[bytes] = None):
        self.static_root: bytes = static_root or _genesis_root()
        self.dynamic: list[ContextBlock] = []
        self._seq: int = 0
        self._pending_seq: Optional[int] = None
        self._last_acked_seq: int = -1
        self._last_seen_seq: Optional[int] = None
        self._last_sent_ack: Optional[AckPacket] = None

    def add_turn(self, role: str, raw_text: str, summary: str) -> ContextBlock:
        """Add a turn to the dynamic (pending) window."""
        block = ContextBlock.from_text(self._seq, role, raw_text, summary)
        self.dynamic.append(block)
        self._seq += 1
        return block

    def build_sync_packet(self) -> SyncPacket:
        """Serialize dynamic window into a SYNC packet ready to transmit."""
        if not self.dynamic:
            raise ValueError("No dynamic blocks to sync.")
        dynamic_data = _compress_blocks(self.dynamic)
        combined_hash = hashlib.sha256(self.static_root + dynamic_data).digest()
        self._pending_seq = self._seq - 1
        return SyncPacket(
            seq=self._pending_seq,
            static_root=self.static_root,
            dynamic_data=dynamic_data,
            combined_hash=combined_hash,
        )

    def acknowledge(self, seq: int) -> bytes:
        """Fold dynamic into static root after receiving ACK. Returns new root."""
        if seq != self._pending_seq:
            raise ValueError(f"ACK seq {seq} does not match pending {self._pending_seq}")
        for block in self.dynamic:
            self.static_root = _fold_block(self.static_root, block)
        self.dynamic.clear()
        self._last_acked_seq = seq
        self._pending_seq = None
        return self.static_root

    def ingest_sync(self, packet: SyncPacket) -> list[ContextBlock]:
        """Validate and ingest an incoming SYNC packet."""
        if packet.seq <= self._last_acked_seq:
            raise ValueError(
                f"Replay detected: SYNC seq {packet.seq} <= last_acked_seq {self._last_acked_seq}"
            )
        if (packet.seq == self._last_seen_seq
                and packet.static_root == self.static_root
                and self._last_sent_ack is not None):
            return []
        if not packet.verify():
            raise ValueError("SYNC packet combined_hash verification failed.")
        if packet.static_root != self.static_root:
            raise ValueError(
                f"Static root mismatch. "
                f"Expected {self.static_root.hex()[:16]}... "
                f"Got {packet.static_root.hex()[:16]}..."
            )
        blocks = packet.decode_blocks()
        self.dynamic.extend(blocks)
        self._seq = blocks[-1].seq + 1
        self._last_seen_seq = packet.seq
        return blocks

    def build_ack(self, packet: SyncPacket) -> AckPacket:
        """Build ACK after successfully ingesting a SYNC."""
        if (packet.seq == self._last_acked_seq + 1
                and self._last_sent_ack is not None
                and self._last_sent_ack.seq == packet.seq):
            return self._last_sent_ack
        for block in self.dynamic:
            self.static_root = _fold_block(self.static_root, block)
        self.dynamic.clear()
        self._last_acked_seq = packet.seq
        ack = AckPacket(seq=packet.seq, new_root=self.static_root)
        self._last_sent_ack = ack
        return ack
