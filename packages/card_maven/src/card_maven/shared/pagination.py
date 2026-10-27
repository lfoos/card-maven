"""Keyset (cursor) pagination.

A cursor encodes the sort key of the last row returned. The next page is
"rows strictly after that key", which stays correct while rows are inserted or
deleted between requests (unlike OFFSET). Cursors are opaque to clients.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from card_maven.shared.errors import InvalidInputError

CursorValue = str | int | datetime | uuid.UUID | None


@dataclass(frozen=True, slots=True)
class Cursor:
    sort: str
    values: tuple[CursorValue, ...]


def _to_json(value: CursorValue) -> Any:
    if isinstance(value, datetime):
        return {"t": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"u": str(value)}
    return value


def _from_json(value: Any) -> CursorValue:
    if isinstance(value, dict):
        if set(value) == {"t"}:
            return datetime.fromisoformat(value["t"])
        if set(value) == {"u"}:
            return uuid.UUID(value["u"])
        raise ValueError("unknown cursor value")
    if value is None or isinstance(value, str | int):
        return value
    raise ValueError("unknown cursor value")


def encode_cursor(sort: str, values: Sequence[CursorValue]) -> str:
    payload = json.dumps({"s": sort, "v": [_to_json(v) for v in values]}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(token: str, *, expected_sort: str, size: int) -> Cursor:
    """Parse a cursor, rejecting anything malformed or from a different sort."""
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        sort = payload["s"]
        values = tuple(_from_json(v) for v in payload["v"])
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise InvalidInputError("invalid cursor", field="cursor") from exc
    if sort != expected_sort or len(values) != size:
        raise InvalidInputError("cursor does not match this sort order", field="cursor")
    return Cursor(sort=sort, values=values)
