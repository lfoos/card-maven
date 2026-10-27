"""Text normalization shared by validation and matching."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def clean(value: str) -> str:
    """Trim and collapse internal whitespace: "  Bowman   Chrome " -> "Bowman Chrome"."""
    return _WHITESPACE.sub(" ", value).strip()


def like_pattern(query: str) -> str:
    """A safe ``ILIKE`` "contains" pattern: user input can't inject wildcards."""
    escaped = clean(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def slugify(name: str) -> str:
    """Natural-key slug for names: "Upper  Deck" -> "upper-deck"."""
    return "-".join(clean(name).lower().split())
