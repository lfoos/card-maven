"""Extract structured facts from free-text sale and listing titles.

Titles look like "2025 Bowman Chrome JJ Wetherholt 1st Gold Refractor Auto /50 PSA 10".
Parsing is deliberately conservative: it extracts what it can recognize and
flags titles that describe something other than a single card (lots, breaks,
reprints), so they never become comps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

# Graders as they appear in titles -> our canonical codes.
GRADER_ALIASES = {
    "PSA": "PSA",
    "BGS": "BGS",
    "BVG": "BGS",
    "SGC": "SGC",
    "CGC": "CGC",
    "CSG": "CGC",
    "TAG": "TAG",
    "HGA": "HGA",
}
_GRADE_WORDS = r"(?:GEM\s*(?:MT|MINT)|PRISTINE|BLACK\s+LABEL|GOLD\s+LABEL|MINT|NM-MT|NM|EX-MT)"
_GRADERS = "|".join(GRADER_ALIASES)
_GRADED = re.compile(
    rf"\b({_GRADERS})\b(?:\s+{_GRADE_WORDS})*\s*[- ]?\s*(10|[1-9](?:\.5)?)(?![\d/.])",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# 12/50, #12/50, 12 / 50 (serial must not exceed the run)
_SERIAL = re.compile(r"(?<![\w.])#?(\d{1,5})\s*/\s*(\d{1,5})\b")
# /50, #/50, #'d /50, numbered to 50
_RUN_ONLY = re.compile(
    r"(?:(?<![\w])#?\s*/\s*(\d{1,5})\b)|(?:#['\u2019]?d\s*(?:to\s*)?/?\s*(\d{1,5})\b)"
    r"|(?:numbered\s+(?:to\s+)?/?\s*(\d{1,5})\b)",
    re.IGNORECASE,
)
_AUTO = re.compile(
    r"\b(auto|autos|autograph|autographs|autographed|signed|on[- ]card auto)\b", re.I
)
_ROOKIE = re.compile(r"\b(rc|rookie)\b", re.IGNORECASE)
_DISQUALIFIERS = [
    (re.compile(r"\blots?\b", re.I), "lot"),
    (re.compile(r"\b(you|u)\s+pick\b|\bpick\s+(your|ur|a)\b|\bchoose\b", re.I), "pick-your-card"),
    (re.compile(r"\b(case|box|team|random)\s+break\b|\bbreak\s+spot\b", re.I), "break"),
    (re.compile(r"\breprints?\b|\brp\b|\bfacsimile\b", re.I), "reprint"),
    (re.compile(r"\bcustom\b|\bproxy\b|\bart\s+card\b", re.I), "custom"),
    (re.compile(r"\bdigital\b|\bnft\b", re.I), "digital"),
    (
        re.compile(
            "\\b[x\u00d7]\\s?[2-9]\\d*\\b"
            r"|\b\d+\s*(card|cards)\b",
            re.I,
        ),
        "multiple-cards",
    ),
]
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens: "Gold-Refractor #BCP-50" -> [gold, refractor, bcp, 50]."""
    return _TOKEN.findall(text.lower())


def compact(text: str) -> str:
    """Card-number form for comparison: "BCP-50" and "bcp 50" -> "bcp50"."""
    return "".join(tokens(text))


@dataclass(frozen=True, slots=True)
class ParsedTitle:
    title: str
    year: int | None = None
    grader: str | None = None
    grade: Decimal | None = None
    serial: int | None = None
    print_run: int | None = None
    is_autograph: bool = False
    is_rookie: bool = False
    disqualified: str | None = None
    words: tuple[str, ...] = field(default=())

    @property
    def condition(self) -> str:
        return "graded" if self.grader and self.grade is not None else "raw"

    def has_phrase(self, phrase: str) -> bool:
        """All tokens of ``phrase`` appear consecutively in the title."""
        wanted = tokens(phrase)
        if not wanted:
            return False
        n = len(wanted)
        return any(list(self.words[i : i + n]) == wanted for i in range(len(self.words) - n + 1))

    def has_compact(self, value: str) -> bool:
        """The compacted ``value`` (e.g. a card number) appears in the title."""
        needle = compact(value)
        if not needle:
            return False
        joined = "".join(self.words)
        # Require the match to start and end on token boundaries.
        positions = [0]
        for word in self.words:
            positions.append(positions[-1] + len(word))
        starts, ends = set(positions[:-1]), set(positions[1:])
        start = joined.find(needle)
        while start != -1:
            if start in starts and start + len(needle) in ends:
                return True
            start = joined.find(needle, start + 1)
        return False


def parse_title(title: str) -> ParsedTitle:
    text = " ".join(title.split())

    disqualified = next(
        (reason for pattern, reason in _DISQUALIFIERS if pattern.search(text)), None
    )

    grader = grade = None
    graded = _GRADED.search(text)
    if graded:
        grader = GRADER_ALIASES[graded.group(1).upper()]
        grade = Decimal(graded.group(2))
    # Don't let "PSA 10" or the grade be read as a year or serial.
    scrubbed = _GRADED.sub(" ", text)

    year_match = _YEAR.search(scrubbed)
    year = int(year_match.group(1)) if year_match else None

    serial = print_run = None
    for match in _SERIAL.finditer(scrubbed):
        num, run = int(match.group(1)), int(match.group(2))
        if 1 <= num <= run and not (1900 <= num <= 2100):
            serial, print_run = num, run
            break
    if print_run is None:
        run_match = _RUN_ONLY.search(scrubbed)
        if run_match:
            print_run = int(next(g for g in run_match.groups() if g))

    return ParsedTitle(
        title=title,
        year=year,
        grader=grader,
        grade=grade,
        serial=serial,
        print_run=print_run,
        is_autograph=bool(_AUTO.search(text)),
        is_rookie=bool(_ROOKIE.search(text)),
        disqualified=disqualified,
        words=tuple(tokens(scrubbed)),
    )
