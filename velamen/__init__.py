# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""
Velamen — Steganographic communication over LLM token distributions.

Encode secrets into natural-looking LLM-generated text using arithmetic
coding over pre-frozen token probability distributions.
"""

__version__ = "0.1.0"

from velamen.stego import encode, decode
from velamen.channel import freeze, verify
from velamen.hctp import ContextChain, ContextBlock, SyncPacket, AckPacket

__all__ = [
    "encode", "decode",
    "freeze", "verify",
    "ContextChain", "ContextBlock", "SyncPacket", "AckPacket",
]
