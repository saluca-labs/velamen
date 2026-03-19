# Velamen

Steganographic communication over LLM token probability distributions.

Velamen encodes secret messages into natural-looking LLM-generated text using arithmetic coding over pre-frozen token probability distributions. The cover text is indistinguishable from normal model output.

## How it works

1. **Freeze** a channel: query an LLM for token probability distributions at each position along a greedy continuation path. Save as a `.hchan` file.
2. **Encode**: treat the secret message bits as an arithmetic-coded stream and expand them into tokens selected from the frozen distributions. The output reads like normal LLM text.
3. **Decode**: reverse the process -- compress the token sequence back into bits using the same distributions, recovering the original message.

Because both sides share the same frozen distributions, no live LLM inference is needed at encode/decode time.

## Installation

```bash
pip install velamen
# For encrypted channels (recommended):
pip install velamen[crypto]
```

## Quick start

### 1. Freeze a channel

Requires [Ollama](https://ollama.com) running locally with a model pulled:

```bash
velamen freeze --prompt "The quarterly earnings report indicated that" \
    --model phi3:mini --tokens 200 --out channel.hchan
```

### 2. Encode a message

```bash
velamen encode --msg "attack at dawn" --channel channel.hchan --key "shared-secret"
```

Output: natural-looking text with the message hidden inside.

### 3. Decode

```bash
velamen decode --cover "The quarterly earnings..." --channel channel.hchan --key "shared-secret"
```

### Python API

```python
import json
from velamen import encode, decode

with open("channel.hchan") as f:
    channel = json.load(f)

cover = encode("secret message", channel, key="shared-key")
recovered = decode(cover, channel, key="shared-key")
assert recovered == "secret message"
```

## HCTP: Hash-Chain Context Transfer Protocol

Velamen includes HCTP, a protocol for transferring conversational context as compact, tamper-evident, hash-chained payloads. Only deltas cross the wire; full history is a 32-byte root hash.

```python
from velamen import ContextChain

chain = ContextChain()
chain.add_turn("user", "What is the mission status?", "asked about mission status")
chain.add_turn("agent", "All systems nominal.", "confirmed systems nominal")

packet = chain.build_sync_packet()
wire_bytes = packet.serialize()  # 74 bytes + compressed delta
```

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full specification.

## Security

- **Encryption**: ChaCha20-Poly1305 AEAD (via `cryptography` package)
- **Key derivation**: PBKDF2-HMAC-SHA256 (100k iterations)
- **Integrity**: HCTP hash chains provide tamper-evident session history
- **Channel security**: frozen distributions are a pre-shared secret; the `.hchan` file must be exchanged securely

Use `--raw` flag only for testing. Always use encryption for real messages.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (for channel freezing only)
- `cryptography` package (optional but recommended)

## License

Apache License 2.0 -- see [LICENSE](LICENSE).

Copyright 2026 Saluca LLC.
