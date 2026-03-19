# Copyright 2026 Saluca LLC
# Licensed under the Apache License, Version 2.0
"""Velamen CLI entry point."""

import argparse
import json
import sys

from velamen.stego import encode, decode
from velamen.channel import freeze, verify


def main():
    parser = argparse.ArgumentParser(
        prog="velamen",
        description="Steganographic communication over LLM token distributions",
    )
    sub = parser.add_subparsers(dest="cmd")

    # encode
    enc = sub.add_parser("encode", help="Hide a message in LLM-generated text")
    enc.add_argument("--msg", required=True, help="Plaintext message to hide")
    enc.add_argument("--channel", required=True, help=".hchan channel file")
    enc.add_argument("--key", default="", help="Shared passphrase")
    enc.add_argument("--raw", action="store_true", help="Skip encryption")

    # decode
    dec = sub.add_parser("decode", help="Extract a hidden message from cover text")
    dec.add_argument("--cover", required=True, help="Cover text to decode")
    dec.add_argument("--channel", required=True, help=".hchan channel file")
    dec.add_argument("--key", default="", help="Shared passphrase")
    dec.add_argument("--raw", action="store_true", help="Skip decryption")

    # freeze
    frz = sub.add_parser("freeze", help="Generate a frozen channel file")
    frz.add_argument("--prompt", required=True, help="Cover prompt seed")
    frz.add_argument("--model", default="phi3:mini")
    frz.add_argument("--tokens", type=int, default=200, help="Positions to freeze")
    frz.add_argument("--out", required=True, help="Output .hchan file")
    frz.add_argument("--ollama", default="http://localhost:11434")

    # verify
    ver = sub.add_parser("verify", help="Verify a .hchan file integrity")
    ver.add_argument("file")

    args = parser.parse_args()

    if args.cmd == "encode":
        with open(args.channel, encoding="utf-8") as f:
            channel = json.load(f)
        result = encode(args.msg, channel, args.key, args.raw)
        print(result)

    elif args.cmd == "decode":
        with open(args.channel, encoding="utf-8") as f:
            channel = json.load(f)
        result = decode(args.cover, channel, args.key, args.raw)
        print(result)

    elif args.cmd == "freeze":
        channel = freeze(args.prompt, args.model, args.tokens, args.ollama)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(channel, f, indent=2)
        print(f"Channel saved: {args.out}")
        print(f"Fingerprint:  {channel['channel_fingerprint']}")
        print(f"Capacity:     ~{channel['capacity_estimate_bytes']} bytes")

    elif args.cmd == "verify":
        with open(args.file, encoding="utf-8") as f:
            channel = json.load(f)
        ok = verify(channel)
        print(f"File:        {args.file}")
        print(f"Fingerprint: {channel.get('channel_fingerprint', 'N/A')}")
        print(f"Integrity:   {'PASS' if ok else 'FAIL'}")
        print(f"Model:       {channel.get('model')}")
        print(f"Positions:   {channel.get('n_tokens')}")
        print(f"Capacity:    ~{channel.get('capacity_estimate_bytes')} bytes")
        if not ok:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
