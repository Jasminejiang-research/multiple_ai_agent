"""Date-window parsing and stale marking for controlled web results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from dateutil.relativedelta import relativedelta

from schemas import WebSearchResult

RecencyUnit = Literal["days", "weeks", "months", "years"]

_NAMED_WINDOWS: dict[str, tuple[int, RecencyUnit]] = {
    "day": (1, "days"),
    "week": (1, "weeks"),
    "month": (1, "months"),
    "year": (1, "years"),
}
_RECENCY_PATTERN = re.compile(
    r"^last_(?P<amount>[1-9]\d*)_(?P<unit>days?|weeks?|months?|years?)$"
)
_SHORT_RECENCY_PATTERN = re.compile(
    r"^(?P<amount>[1-9]\d*)(?P<unit>[dwmy])$"
)
_SHORT_UNITS: dict[str, RecencyUnit] = {
    "d": "days",
    "w": "weeks",
    "m": "months",
    "y": "years",
}


@dataclass(frozen=True)
class RecencyWindow:
    """A parsed relative calendar window."""

    amount: int
    unit: RecencyUnit

    def cutoff(self, as_of: date) -> date:
        """Return the oldest publication date considered current."""
        return as_of - relativedelta(**{self.unit: self.amount})


def parse_recency(recency: str) -> RecencyWindow:
    """Parse supported recency controls into a deterministic calendar window.

    Accepted values include provider-style names (``month``), explicit names
    such as ``last_12_months``, and compact forms such as ``30d``.
    """
    if not isinstance(recency, str):
        raise TypeError("recency must be a string.")
    normalized = recency.strip().lower()
    if not normalized:
        raise ValueError("recency must not be blank.")

    named_window = _NAMED_WINDOWS.get(normalized)
    if named_window is not None:
        return RecencyWindow(*named_window)

    match = _RECENCY_PATTERN.fullmatch(normalized)
    if match is not None:
        unit = match.group("unit")
        canonical_unit = unit if unit.endswith("s") else f"{unit}s"
        return RecencyWindow(
            amount=int(match.group("amount")),
            unit=canonical_unit,  # type: ignore[arg-type]
        )

    short_match = _SHORT_RECENCY_PATTERN.fullmatch(normalized)
    if short_match is not None:
        return RecencyWindow(
            amount=int(short_match.group("amount")),
            unit=_SHORT_UNITS[short_match.group("unit")],
        )

    raise ValueError(
        "Unsupported recency value. Use day, week, month, year, a compact "
        "value such as 30d, or an explicit value such as last_12_months."
    )


def mark_stale_sources(
    results: list[WebSearchResult],
    recency: str | None,
    *,
    as_of: date | None = None,
) -> list[WebSearchResult]:
    """Keep every result while marking dates older than the requested window."""
    if recency is None:
        return results

    window = parse_recency(recency)
    cutoff = window.cutoff(as_of or datetime.now(timezone.utc).date())
    return [
        result.model_copy(
            update={
                "stale": (
                    result.published_date is not None
                    and result.published_date < cutoff
                )
            }
        )
        for result in results
    ]


def to_tavily_time_range(recency: str) -> str | None:
    """Map a local window to Tavily's broadest useful time-range control."""
    window = parse_recency(recency)

    if window.unit == "days":
        if window.amount <= 1:
            return "day"
        if window.amount <= 7:
            return "week"
        if window.amount <= 31:
            return "month"
        if window.amount <= 366:
            return "year"
    elif window.unit == "weeks":
        if window.amount <= 1:
            return "week"
        if window.amount <= 4:
            return "month"
        if window.amount <= 52:
            return "year"
    elif window.unit == "months":
        if window.amount <= 1:
            return "month"
        if window.amount <= 12:
            return "year"
    elif window.unit == "years" and window.amount <= 1:
        return "year"

    return None
