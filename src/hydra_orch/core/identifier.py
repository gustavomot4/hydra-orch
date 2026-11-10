"""UUIDv7 identifiers across the supported Python versions."""

import secrets
import time
import uuid


def new_id() -> str:
    native = getattr(uuid, "uuid7", None)
    if native is not None:
        return str(native())
    milliseconds = time.time_ns() // 1_000_000
    value = (milliseconds << 80) | (7 << 76) | (secrets.randbits(12) << 64)
    return str(uuid.UUID(int=value | (2 << 62) | secrets.randbits(62)))
