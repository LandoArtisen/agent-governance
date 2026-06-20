"""RFC 8785 JSON Canonicalization Scheme (JCS), pure standard library.

A hash chain is only useful if everyone computes the same hash from the same
record. Plain `json.dumps` does not guarantee that: key order, whitespace, and
number formatting vary across languages and settings, so a record sealed by one
implementation can fail verification in another. JCS pins all of that down, so
`SHA-256(canonicalize(record))` is stable across implementations.

This matters because the IETF agent-audit-trail draft mandates exactly this:
records linked by `prev_hash(N) = hex(SHA-256(JCS(record(N-1))))`, and
"Alternative canonicalization schemes MUST NOT be used, as they would break
chain verification across implementations." RFC 8785 itself is a ratified RFC.

Scope: this implements JCS for the JSON value types the library actually emits
(objects, arrays, strings, booleans, null, and finite numbers). Non-finite
numbers are rejected, because JCS, like JSON, has no representation for them,
and a non-finite value in an audit record is a bug we want to surface, not hash.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _number(n: float | int) -> str:
    """Serialize a number the way ECMAScript / RFC 8785 section 3.2.2 does.

    Integers print without a decimal point; integer-valued floats lose their
    trailing ".0"; exponents drop leading zeros and always carry a sign. Good
    for the finite values an audit record carries (a timestamp is the only one).
    """
    if isinstance(n, bool):  # bool is an int subclass; never reach here via dispatch
        raise TypeError("bool is not a JCS number")
    if isinstance(n, int):
        return str(n)
    if not math.isfinite(n):
        raise ValueError("JCS cannot serialize NaN or Infinity")
    if n == 0:
        return "0"  # also collapses -0.0 to "0"
    if float(n).is_integer() and abs(n) < 1e21:
        return str(int(n))
    r = repr(n)  # Python's repr is the shortest round-tripping form
    if "e" in r or "E" in r:
        mantissa, _, exp = r.replace("E", "e").partition("e")
        sign = "-" if exp.startswith("-") else "+"
        exp = exp.lstrip("+-").lstrip("0") or "0"
        r = f"{mantissa}e{sign}{exp}"
    return r


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # json's string escaping already matches JCS: short escapes for the
        # control characters, \u00xx for the rest, non-ASCII passed through.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, dict):
        # Keys are sorted by their UTF-16 code units, per the spec.
        items = sorted(value.items(), key=lambda kv: str(kv[0]).encode("utf-16-be"))
        inner = ",".join(f"{json.dumps(str(k), ensure_ascii=False)}:{_encode(v)}"
                         for k, v in items)
        return "{" + inner + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(v) for v in value) + "]"
    raise TypeError(f"JCS cannot serialize {type(value).__name__}")


def canonicalize(value: Any) -> str:
    """Return the RFC 8785 canonical JSON string for a JSON-compatible value."""
    return _encode(value)


def canonical_hash(value: Any) -> str:
    """SHA-256 hex digest of the canonical form. The chain primitive."""
    return hashlib.sha256(canonicalize(value).encode("utf-8")).hexdigest()
