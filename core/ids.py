# core/ids.py — SDD §3 / D3
from hashlib import blake2b


def content_id(*parts: str) -> str:
    """Compute deterministic 32-hex content ID using blake2b (digest_size=16).

    Uses ASCII unit separator \x1f between parts to prevent separator collisions.
    """
    return blake2b("\x1f".join(parts).encode("utf-8"), digest_size=16).hexdigest()
