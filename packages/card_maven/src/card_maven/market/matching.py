"""Decide whether a parsed title describes a specific card variant.

Scoring is rule-based and explainable: each check either rejects the title
outright or adds weight. A title is a match at ``MATCH_THRESHOLD`` or above.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from card_maven.catalog.models import CardVariant
from card_maven.market.parsing import ParsedTitle, tokens

MATCH_THRESHOLD = Decimal("0.75")
METHOD = "rules_v1"

# Words that signal a parallel on most modern products. Extended at runtime
# with the set's own parallels and the eBay Taxonomy vocabulary.
DEFAULT_PARALLEL_TERMS = frozenset(
    {
        "refractor", "xfractor", "superfractor", "silver", "gold", "orange", "red", "blue",
        "green", "purple", "pink", "black", "aqua", "teal", "yellow", "bronze", "sapphire",
        "shimmer", "wave", "mojo", "atomic", "speckle", "sparkle", "lava", "holo", "camo",
        "disco", "hyper", "zebra", "checkerboard", "snakeskin", "neon", "ruby", "emerald",
        "platinum", "rainbow", "foil", "cracked", "geometric", "shock", "velocity", "scope",
        "tiger", "dragon", "lazer", "laser", "prizm", "mosaic", "fluorescent", "logofractor",
    }
)  # fmt: skip

WEIGHTS = {
    "year": Decimal("0.15"),
    "number": Decimal("0.45"),
    "names": Decimal("0.35"),
    "parallel": Decimal("0.15"),
    "print_run": Decimal("0.10"),
    "autograph": Decimal("0.05"),
}


@dataclass(frozen=True, slots=True)
class MatchTarget:
    """What a title must say to be this card."""

    variant_id: object
    year: int
    card_number: str
    surnames: tuple[str, ...]
    parallel_name: str | None  # None means the base card
    print_run: int | None
    is_autograph: bool
    # Parallel words that would mean "a different parallel" if present.
    conflicting_terms: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class MatchResult:
    confidence: Decimal
    reasons: tuple[str, ...]

    @property
    def is_match(self) -> bool:
        return self.confidence >= MATCH_THRESHOLD


def _reject(reason: str) -> MatchResult:
    return MatchResult(Decimal(0), (reason,))


def build_target(variant: CardVariant, vocabulary: Iterable[str] = ()) -> MatchTarget:
    """Target for a catalog variant. ``vocabulary`` adds known parallel names."""
    card = variant.card
    parallel = variant.parallel
    is_base = parallel.is_base
    own = set(tokens(parallel.name)) if not is_base else set()
    # Words that are part of the card's own identity never signal a parallel:
    # "Prizm" in a Prizm set, "Green" in "Green Bay Packers", "Gold" in a name.
    identity = set(tokens(card.card_set.name)) | set(tokens(card.team or ""))
    identity |= {t for p in card.players for t in tokens(p.full_name)}
    identity |= set(tokens(card.subset or "")) | set(tokens(card.name))
    terms = set(DEFAULT_PARALLEL_TERMS)
    for phrase in vocabulary:
        terms.update(tokens(phrase))
    for other in card.card_set.parallels:
        if not other.is_base:
            terms.update(tokens(other.name))
    terms -= identity | own | {"base", "chrome", "1st", "first"}
    surnames = tuple(tokens(p.full_name)[-1] for p in card.players if tokens(p.full_name))
    return MatchTarget(
        variant_id=variant.id,
        year=card.card_set.year,
        card_number=card.card_number,
        surnames=surnames,
        parallel_name=None if is_base else parallel.name,
        print_run=parallel.print_run,
        is_autograph=bool(card.is_autograph),
        conflicting_terms=frozenset(terms),
    )


def score(parsed: ParsedTitle, target: MatchTarget) -> MatchResult:
    if parsed.disqualified:
        return _reject(f"disqualified: {parsed.disqualified}")
    if parsed.year != target.year:
        return _reject("year differs" if parsed.year else "no year")
    if target.is_autograph != parsed.is_autograph:
        return _reject("autograph mismatch")
    if target.print_run and parsed.print_run and parsed.print_run != target.print_run:
        return _reject(f"print run /{parsed.print_run} is not /{target.print_run}")
    if target.print_run is None and parsed.print_run is not None:
        return _reject("numbered card, but this variant isn't numbered")

    conflicts = sorted(t for t in target.conflicting_terms if t in parsed.words)
    if conflicts:
        return _reject(f"different parallel ({', '.join(conflicts)})")
    if target.parallel_name and not all(parsed.has_phrase(t) for t in tokens(target.parallel_name)):
        return _reject(f"missing parallel '{target.parallel_name}'")

    total = WEIGHTS["year"] + WEIGHTS["parallel"]
    reasons = ["year", "parallel"]
    if parsed.has_compact(target.card_number):
        total += WEIGHTS["number"]
        reasons.append("number")
    if target.surnames and all(s in parsed.words for s in target.surnames):
        total += WEIGHTS["names"]
        reasons.append("names")
    if "number" not in reasons and "names" not in reasons:
        return _reject("neither card number nor player names")
    if target.print_run and parsed.print_run == target.print_run:
        total += WEIGHTS["print_run"]
        reasons.append("print_run")
    if target.is_autograph and parsed.is_autograph:
        total += WEIGHTS["autograph"]
        reasons.append("autograph")
    return MatchResult(min(total, Decimal(1)), tuple(reasons))
