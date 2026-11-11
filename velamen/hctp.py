# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
HCTP -- Hash-Chain Context Transfer Protocol
=============================================
Reference implementation of draft-ruvalcaba-hctp-01.

Acknowledged history is a 32-byte static root; only the pending blocks (the
dynamic window) cross the wire. Section numbers in comments refer to
draft-ruvalcaba-hctp-01.

The protocol state is split as Section 6.1 requires: `HctpSender` holds the
sender state of one directional chain and `HctpReceiver` the receiver state of
one directional chain. A bidirectional endpoint holds one of each (Section 7);
`ContextChain` bundles the two without sharing any state between them.

Every object here is bound to one scope instance (Section 10): create new
objects when the scope instance ends, and never reuse them across instances.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Optional, Union

PROTO_VERSION = 0x01
PTYPE_SYNC = 0x53   # 'S'
PTYPE_ACK = 0x41    # 'A'
GENESIS_SEED = b"hctp-genesis-v1"

# Section 9
MAX_SUMMARY_LEN = 120             # Unicode code points
MAX_ROLE_LEN = 64                 # octets of the UTF-8 encoding
MAX_BLOCKS_PER_SYNC_BASE = 64
MAX_DECOMPRESSED_LEN_BASE = 65536
SYNC_HEADER_LEN = 42              # fixed header prefix, read first
SYNC_FIXED_LEN = 74               # header prefix + combined_hash
ACK_LEN = 38
MAX_SEQ = 0xFFFFFFFF

DEFAULT_MAX_RETRANSMITS = 3

_HEX64 = re.compile(r"[0-9a-f]{64}")
_SHORT_ESCAPES = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r"}
_MEMBERS = ("content_hash", "role", "seq", "summary")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class HctpError(ValueError):
    """Base class. Subclasses ValueError so existing callers keep working."""


class InvalidBlock(HctpError):
    """A block that has no canonical encoding under Section 3.1."""


class PacketError(HctpError):
    """A transport unit that is not exactly one well-formed packet (Sections 5, 10).

    `reason` is one of: too_short, unknown_version, unknown_packet_type,
    dynamic_len_too_large, length_mismatch.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


class Rejected(HctpError):
    """A non-fatal rejection: the packet was discarded, no state changed, nothing is sent."""

    def __init__(self, step: str, detail: str = ""):
        super().__init__(f"rejected at {step}: {detail}" if detail else f"rejected at {step}")
        self.step = step


class FatalSessionError(HctpError):
    """Static-root mismatch or ACK divergence (Section 6.6). The session has ended."""


class SessionEnded(HctpError):
    """The object's session has ended; start a new session from the genesis root."""


# --------------------------------------------------------------------------
# Canonical encoding (Section 3.1, RFC 8785)
# --------------------------------------------------------------------------

def _jcs_string(s: str) -> str:
    """RFC 8785 section 3.2.2.2: escape only '"', '\\' and U+0000..U+001F."""
    if not isinstance(s, str):
        raise InvalidBlock(f"expected a string, got {type(s).__name__}")
    out = ['"']
    for ch in s:
        c = ord(ch)
        if 0xD800 <= c <= 0xDFFF:
            raise InvalidBlock("unpaired surrogate: not well-formed UTF-8")
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif c < 0x20:
            out.append(_SHORT_ESCAPES.get(c, f"\\u{c:04x}"))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _check_encodable(seq, role, content_hash, summary) -> None:
    """What canonical(B) itself needs: a seq in range and four well-formed strings."""
    # bool is an int subclass in Python; a JSON true is not a seq.
    if type(seq) is not int or not 0 <= seq <= MAX_SEQ:
        raise InvalidBlock(f"seq must be an integer in 0..{MAX_SEQ}, got {seq!r}")
    for name, value in (("content_hash", content_hash), ("role", role), ("summary", summary)):
        if not isinstance(value, str):
            raise InvalidBlock(f"{name} must be a string")


def _check_valid(seq, role, content_hash, summary) -> None:
    """The validity conditions of Section 3.1, applied at origination and at ingest (6.3)."""
    _check_encodable(seq, role, content_hash, summary)
    if not _HEX64.fullmatch(content_hash):
        raise InvalidBlock("content_hash must be exactly 64 lowercase hex digits")
    try:
        role_octets = len(role.encode("utf-8"))
        summary.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidBlock("not well-formed UTF-8 (unpaired surrogate)") from exc
    if not 1 <= role_octets <= MAX_ROLE_LEN:
        raise InvalidBlock(f"role must be 1..{MAX_ROLE_LEN} octets, got {role_octets}")
    if len(summary) > MAX_SUMMARY_LEN:  # str length counts code points
        raise InvalidBlock(f"summary exceeds {MAX_SUMMARY_LEN} code points")


@dataclass
class ContextBlock:
    """A single conversation turn (Section 3.1)."""
    seq: int
    role: str
    content_hash: str
    summary: str

    @staticmethod
    def from_text(seq: int, role: str, raw_text: str, summary: str) -> "ContextBlock":
        """Build a block from raw turn text. No Unicode normalization is applied."""
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        block = ContextBlock(seq=seq, role=role, content_hash=content_hash, summary=summary)
        block.validate()
        return block

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "role": self.role,
            "content_hash": self.content_hash,
            "summary": self.summary,
        }

    @staticmethod
    def from_dict(d: dict) -> "ContextBlock":
        """Build a block from exactly the four members of Section 3.1."""
        if set(d) != set(_MEMBERS):
            raise InvalidBlock(f"a block has exactly the members {_MEMBERS}, got {sorted(d)}")
        return ContextBlock(
            seq=d["seq"], role=d["role"],
            content_hash=d["content_hash"], summary=d["summary"],
        )

    def validate(self) -> None:
        """Raise InvalidBlock unless the block meets every condition of Section 3.1."""
        _check_valid(self.seq, self.role, self.content_hash, self.summary)

    def canonical_bytes(self) -> bytes:
        """canonical(B): the RFC 8785 serialization, raw UTF-8, members in code-point order.

        Encoding needs only a seq in range and well-formed strings (an unpaired
        surrogate is refused). The length and content_hash limits are validity
        conditions checked by validate(), by from_text and by a receiver at ingest.
        """
        _check_encodable(self.seq, self.role, self.content_hash, self.summary)
        body = ",".join((
            f'"content_hash":{_jcs_string(self.content_hash)}',
            f'"role":{_jcs_string(self.role)}',
            f'"seq":{self.seq}',
            f'"summary":{_jcs_string(self.summary)}',
        ))
        return ("{" + body + "}").encode("utf-8")


def encode_block_array(blocks: list[ContextBlock]) -> bytes:
    """The canonical block array of Section 3.1: '[' blocks joined by ',' ']', no whitespace."""
    return b"[" + b",".join(b.canonical_bytes() for b in blocks) + b"]"


def _reject_constant(name: str):
    raise InvalidBlock(f"{name} is not JSON")


def _no_duplicates(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise InvalidBlock(f"duplicate member {k!r}")
        seen[k] = v
    return seen


def parse_block_array(raw: bytes, max_blocks: int = MAX_BLOCKS_PER_SYNC_BASE) -> list[ContextBlock]:
    """Parse decompressed dynamic_data and require it to be exactly canonical (Section 6.3 step 6).

    Raises InvalidBlock for anything that is not the canonical encoding of a non-empty
    array of valid blocks. Ordering and contiguity of seq are checked by the receiver.
    """
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_no_duplicates,
                            parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidBlock(f"not well-formed UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise InvalidBlock("dynamic_data must decode to a non-empty array")
    if len(parsed) > max_blocks:
        raise InvalidBlock(f"{len(parsed)} blocks exceeds the accepted bound {max_blocks}")
    blocks = []
    for item in parsed:
        if not isinstance(item, dict):
            raise InvalidBlock("every array element must be an object")
        block = ContextBlock.from_dict(item)
        block.validate()
        blocks.append(block)
    if encode_block_array(blocks) != raw:
        raise InvalidBlock("octets differ from the canonical encoding")
    return blocks


# --------------------------------------------------------------------------
# Rolling root (Section 4)
# --------------------------------------------------------------------------

def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _genesis_root() -> bytes:
    return _sha(GENESIS_SEED)


def genesis_root() -> bytes:
    """root_0 = SHA256("hctp-genesis-v1")."""
    return _genesis_root()


def _fold_block(root: bytes, block: ContextBlock) -> bytes:
    """fold(R, B) = SHA256(R || SHA256(canonical(B)))."""
    return _sha(root + _sha(block.canonical_bytes()))


def fold(root: bytes, block: ContextBlock) -> bytes:
    return _fold_block(root, block)


# --------------------------------------------------------------------------
# zlib (Sections 5.1, 6.3, 11)
# --------------------------------------------------------------------------

def _compress(raw: bytes) -> bytes:
    data = zlib.compress(raw, level=9)
    if data[1] & 0x20:  # FDICT; zlib.compress never sets it, but say so rather than assume
        raise HctpError("zlib produced a stream with FDICT set")
    return data


def _strict_decompress(data: bytes, max_len: int) -> bytes:
    """Exactly one complete zlib stream, FDICT clear, ending at the last octet, output bounded."""
    if len(data) < 2:
        raise InvalidBlock("dynamic_data too short for a zlib stream")
    if data[1] & 0x20:
        raise InvalidBlock("zlib FDICT flag set")
    d = zlib.decompressobj()
    try:
        out = d.decompress(data, max_len + 1)
    except zlib.error as exc:
        raise InvalidBlock(f"zlib: {exc}") from exc
    if len(out) > max_len:
        raise InvalidBlock(f"decompressed output exceeds the accepted bound {max_len}")
    if not d.eof:
        raise InvalidBlock("truncated zlib stream")
    if d.unused_data or d.unconsumed_tail:
        raise InvalidBlock("octets after the end of the zlib stream")
    return out


# --------------------------------------------------------------------------
# Packets (Section 5)
# --------------------------------------------------------------------------

@dataclass
class SyncPacket:
    """SYNC wire packet (Section 5.1)."""
    seq: int
    static_root: bytes
    dynamic_data: bytes
    combined_hash: bytes

    def serialize(self) -> bytes:
        return (
            struct.pack(">BBI", PROTO_VERSION, PTYPE_SYNC, self.seq)
            + self.static_root
            + struct.pack(">I", len(self.dynamic_data))
            + self.dynamic_data
            + self.combined_hash
        )

    @staticmethod
    def deserialize(data: bytes, max_dynamic_len: int = MAX_DECOMPRESSED_LEN_BASE) -> "SyncPacket":
        """Framing and version check of Section 6.3 step 1. The unit must be exactly one SYNC."""
        pkt = parse_packet(data, max_dynamic_len)
        if not isinstance(pkt, SyncPacket):
            raise PacketError("unknown_packet_type", "expected SYNC (0x53), got ACK")
        return pkt

    def verify(self) -> bool:
        """Recompute combined_hash over static_root and dynamic_data as received."""
        return _sha(self.static_root + self.dynamic_data) == self.combined_hash

    def decode_blocks(self, max_decompressed: int = MAX_DECOMPRESSED_LEN_BASE,
                      max_blocks: int = MAX_BLOCKS_PER_SYNC_BASE) -> list[ContextBlock]:
        """Strictly decode dynamic_data: one zlib stream, canonical non-empty block array."""
        if not self.dynamic_data:
            raise InvalidBlock("dynamic_len is zero")
        raw = _strict_decompress(self.dynamic_data, max_decompressed)
        return parse_block_array(raw, max_blocks)


@dataclass
class AckPacket:
    """ACK wire packet (Section 5.2): exactly 38 octets."""
    seq: int
    new_root: bytes

    def serialize(self) -> bytes:
        return struct.pack(">BBI", PROTO_VERSION, PTYPE_ACK, self.seq) + self.new_root

    @staticmethod
    def deserialize(data: bytes) -> "AckPacket":
        pkt = parse_packet(data)
        if not isinstance(pkt, AckPacket):
            raise PacketError("unknown_packet_type", "expected ACK (0x41), got SYNC")
        return pkt


def parse_packet(data: bytes, max_dynamic_len: int = MAX_DECOMPRESSED_LEN_BASE
                 ) -> Union[SyncPacket, AckPacket]:
    """Decode one transport unit that must hold exactly one packet (Sections 5, 10).

    dynamic_len is compared with `max_dynamic_len` before dynamic_data is read.
    """
    data = bytes(data)
    if len(data) < 2:
        raise PacketError("too_short", f"{len(data)} octets")
    version, ptype = data[0], data[1]
    if version != PROTO_VERSION:
        raise PacketError("unknown_version", f"0x{version:02x}")
    if ptype == PTYPE_ACK:
        if len(data) != ACK_LEN:
            raise PacketError("length_mismatch", f"ACK of {len(data)} octets")
        seq, = struct.unpack_from(">I", data, 2)
        return AckPacket(seq=seq, new_root=data[6:38])
    if ptype != PTYPE_SYNC:
        raise PacketError("unknown_packet_type", f"0x{ptype:02x}")
    if len(data) < SYNC_FIXED_LEN:
        raise PacketError("too_short", f"SYNC of {len(data)} octets")
    seq, = struct.unpack_from(">I", data, 2)
    dyn_len, = struct.unpack_from(">I", data, 38)
    if dyn_len > max_dynamic_len:
        raise PacketError("dynamic_len_too_large", f"{dyn_len} > {max_dynamic_len}")
    if len(data) != SYNC_FIXED_LEN + dyn_len:
        raise PacketError("length_mismatch",
                          f"{len(data)} octets, header says {SYNC_FIXED_LEN + dyn_len}")
    return SyncPacket(
        seq=seq,
        static_root=data[6:38],
        dynamic_data=data[SYNC_HEADER_LEN:SYNC_HEADER_LEN + dyn_len],
        combined_hash=data[SYNC_HEADER_LEN + dyn_len:],
    )


def _wire(packet: Union[bytes, bytearray, SyncPacket, AckPacket]) -> bytes:
    if isinstance(packet, (SyncPacket, AckPacket)):
        return packet.serialize()
    return bytes(packet)


# --------------------------------------------------------------------------
# Receiver (Sections 6.1, 6.3)
# --------------------------------------------------------------------------

@dataclass
class ReceiveResult:
    """Outcome of HctpReceiver.receive.

    outcome is "accepted" (blocks folded, ack is new) or "duplicate" (exact
    retransmission, ack is the cached ACK, nothing folded).
    """
    outcome: str
    ack: AckPacket
    blocks: list[ContextBlock]

    @property
    def ack_bytes(self) -> bytes:
        return self.ack.serialize()


class HctpReceiver:
    """Receiver state for one directional chain (Section 6.1)."""

    def __init__(self, max_blocks: int = MAX_BLOCKS_PER_SYNC_BASE,
                 max_decompressed: int = MAX_DECOMPRESSED_LEN_BASE):
        if max_blocks < MAX_BLOCKS_PER_SYNC_BASE or max_decompressed < MAX_DECOMPRESSED_LEN_BASE:
            raise ValueError("receiver bounds must be at least the Section 9 baselines")
        self.max_blocks = max_blocks
        self.max_decompressed = max_decompressed
        self.ended = False
        self._reset()

    def _reset(self) -> None:
        self.local_root: bytes = _genesis_root()
        self.last_seen_seq: Optional[int] = None
        self.last_block_seq: Optional[int] = None
        self.has_seen = False
        # ack_cache: (cached ACK, pre-fold root, SHA-256 of the accepted SYNC octets)
        self.ack_cache: Optional[tuple[AckPacket, bytes, bytes]] = None

    def end(self) -> None:
        """End the session: discard all receiver state (Section 6.6)."""
        self._reset()
        self.ended = True

    def receive(self, packet: Union[bytes, SyncPacket]) -> ReceiveResult:
        """Apply the ordered checks of Section 6.3 to one received transport unit.

        Raises Rejected for every non-fatal rejection (no state change, send
        nothing) and FatalSessionError on a static-root mismatch, after which
        this receiver's session has ended.
        """
        if self.ended:
            raise SessionEnded("this receiver's session has ended")
        octets = _wire(packet)

        # 1. Framing and version (dynamic_len bounded before dynamic_data is read).
        try:
            p = SyncPacket.deserialize(octets, self.max_decompressed)
        except PacketError as exc:
            raise Rejected("framing", str(exc)) from exc

        # 2. Integrity.
        if not p.verify():
            raise Rejected("integrity", "combined_hash mismatch")

        # 3. Replay.
        if self.has_seen and p.seq < self.last_seen_seq:
            raise Rejected("replay", f"seq {p.seq} < last_seen_seq {self.last_seen_seq}")

        # 4. Duplicate: digest of the complete received octets against the cached digest.
        if self.has_seen and p.seq == self.last_seen_seq:
            cached_ack, _pre_fold_root, digest = self.ack_cache
            if _sha(octets) == digest:
                return ReceiveResult("duplicate", cached_ack, [])
            raise Rejected("duplicate", "same seq, different octets")

        # 5. Alignment: the only fatal check.
        if p.static_root != self.local_root:
            self.end()
            raise FatalSessionError("static-root mismatch: the session has ended")

        # 6. Ingest validation.
        try:
            blocks = p.decode_blocks(self.max_decompressed, self.max_blocks)
        except InvalidBlock as exc:
            raise Rejected("ingest", str(exc)) from exc
        expected = 0 if self.last_block_seq is None else self.last_block_seq + 1
        for i, b in enumerate(blocks):
            if b.seq != expected + i:
                raise Rejected("ingest", f"seq {b.seq} where {expected + i} was expected")
        if blocks[-1].seq != p.seq:
            raise Rejected("ingest", f"packet seq {p.seq} != last block seq {blocks[-1].seq}")

        # 7. Accept.
        pre_fold_root = self.local_root
        root = pre_fold_root
        for b in blocks:
            root = _fold_block(root, b)
        self.local_root = root
        self.last_block_seq = blocks[-1].seq
        self.last_seen_seq = p.seq
        self.has_seen = True
        ack = AckPacket(seq=p.seq, new_root=root)
        self.ack_cache = (ack, pre_fold_root, _sha(octets))
        return ReceiveResult("accepted", ack, blocks)


# --------------------------------------------------------------------------
# Sender (Sections 6.1, 6.2, 6.4, 6.5)
# --------------------------------------------------------------------------

class HctpSender:
    """Sender state for one directional chain (Section 6.1)."""

    def __init__(self, max_retransmits: int = DEFAULT_MAX_RETRANSMITS):
        self.max_retransmits = max_retransmits
        self.ended = False
        self._reset()

    def _reset(self) -> None:
        self.static_root: bytes = _genesis_root()
        self.dynamic: list[ContextBlock] = []
        self.queue: list[ContextBlock] = []
        self.next_seq = 0
        self.pending_seq: Optional[int] = None
        self.last_acked_seq: Optional[int] = None    # undefined until the first ACK
        self._frozen = False                         # a window W is being sent in parts
        self._part: list[ContextBlock] = []          # blocks of the outstanding SYNC
        self._last_sync: Optional[bytes] = None      # retained for octet-identical retransmit
        self.retransmits = 0

    def end(self) -> None:
        """End the session: discard all sender state (Section 6.6)."""
        self._reset()
        self.ended = True

    def _check_open(self) -> None:
        if self.ended:
            raise SessionEnded("this sender's session has ended")

    def add_turn(self, role: str, raw_text: str, summary: str) -> ContextBlock:
        """Originate a block. Its seq is assigned now; it is queued while the window is frozen."""
        self._check_open()
        if self.next_seq > MAX_SEQ:
            self.end()
            raise SessionEnded("seq space exhausted; start a new session")
        block = ContextBlock.from_text(self.next_seq, role, raw_text, summary)
        self.next_seq += 1
        (self.queue if self._frozen else self.dynamic).append(block)
        return block

    @property
    def outstanding(self) -> bool:
        return self.pending_seq is not None

    def _first_part(self) -> list[ContextBlock]:
        """The longest prefix of the window within both Section 9 baselines."""
        part: list[ContextBlock] = []
        size = 1  # the closing bracket; '[' and each ',' are counted per block below
        for b in self.dynamic:
            n = len(b.canonical_bytes()) + 1
            if len(part) == MAX_BLOCKS_PER_SYNC_BASE or size + n > MAX_DECOMPRESSED_LEN_BASE:
                break
            part.append(b)
            size += n
        return part

    def _emit(self) -> SyncPacket:
        part = self._first_part()
        dynamic_data = _compress(encode_block_array(part))
        pkt = SyncPacket(
            seq=part[-1].seq,
            static_root=self.static_root,
            dynamic_data=dynamic_data,
            combined_hash=_sha(self.static_root + dynamic_data),
        )
        self._part = part
        self.pending_seq = pkt.seq
        self._last_sync = pkt.serialize()
        self.retransmits = 0
        return pkt

    def build_sync(self) -> SyncPacket:
        """Freeze the dynamic window and build the SYNC for its first part (Section 6.2).

        The static root is not advanced here; it advances only on a valid ACK.
        """
        self._check_open()
        if self.outstanding:
            raise HctpError("a SYNC is outstanding; retransmit it or wait for its ACK")
        if not self.dynamic:
            raise HctpError("no pending blocks to send")
        self._frozen = True
        return self._emit()

    def retransmit(self) -> bytes:
        """Octet-identical copy of the outstanding SYNC (Section 6.5).

        When the bounded count is exhausted the session ends and SessionEnded is raised.
        """
        self._check_open()
        if not self.outstanding:
            raise HctpError("no SYNC is outstanding")
        if self.retransmits >= self.max_retransmits:
            self.end()
            raise SessionEnded("retransmit count exhausted: transport failure")
        self.retransmits += 1
        return self._last_sync

    def receive_ack(self, ack: Union[bytes, AckPacket]) -> Optional[SyncPacket]:
        """Process an ACK (Section 6.4).

        Returns the SYNC for the next part when the frozen window was split, else None.
        Raises Rejected when the ACK is discarded without state change, and
        FatalSessionError (session ended) when new_root differs from the candidate root.
        """
        self._check_open()
        if isinstance(ack, AckPacket):
            a = ack
        else:
            try:
                a = AckPacket.deserialize(ack)
            except PacketError as exc:
                raise Rejected("framing", str(exc)) from exc
        if self.pending_seq is None or a.seq != self.pending_seq:
            raise Rejected("ack", f"seq {a.seq} is not the outstanding {self.pending_seq}")
        if self.last_acked_seq is not None and a.seq <= self.last_acked_seq:
            raise Rejected("ack", f"seq {a.seq} <= last_acked_seq {self.last_acked_seq}")
        candidate = self.static_root
        for b in self._part:
            candidate = _fold_block(candidate, b)
        if a.new_root != candidate:
            self.end()
            raise FatalSessionError("ACK new_root differs from the candidate root: session ended")
        self.static_root = candidate
        del self.dynamic[:len(self._part)]
        self._part = []
        self.last_acked_seq = a.seq
        self.pending_seq = None
        self._last_sync = None
        self.retransmits = 0
        if self.dynamic:
            return self._emit()
        self._frozen = False
        self.dynamic.extend(self.queue)
        self.queue.clear()
        return None


# --------------------------------------------------------------------------
# Convenience: one endpoint, both directions, state kept separate (Section 7)
# --------------------------------------------------------------------------

class ContextChain:
    """One endpoint: an outbound HctpSender and an inbound HctpReceiver.

    The two share no state (Section 6.1). Each is one directional chain with its
    own seq space starting at 0 (Section 7). The chain a SYNC belongs to is the
    direction it arrived on, never a block's role.
    """

    def __init__(self, max_retransmits: int = DEFAULT_MAX_RETRANSMITS):
        self.sender = HctpSender(max_retransmits=max_retransmits)
        self.receiver = HctpReceiver()

    # outbound chain
    def add_turn(self, role: str, raw_text: str, summary: str) -> ContextBlock:
        return self.sender.add_turn(role, raw_text, summary)

    def build_sync_packet(self) -> SyncPacket:
        return self.sender.build_sync()

    def acknowledge(self, ack: Union[bytes, AckPacket]) -> bytes:
        """Process an ACK for the outbound chain and return the sender's static root."""
        if isinstance(ack, int):
            raise TypeError("-01 checks the ACK's new_root: pass the AckPacket or its octets")
        self.sender.receive_ack(ack)
        return self.sender.static_root

    # inbound chain
    def ingest_sync(self, packet: Union[bytes, SyncPacket]) -> ReceiveResult:
        return self.receiver.receive(packet)

    def end(self) -> None:
        """End the session on both chains (the scope instance ended)."""
        self.sender.end()
        self.receiver.end()
