"""Schemas for controlled web research results."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any

from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceQuality(str, Enum):
    """Quality category assigned to a controlled web research source."""

    OFFICIAL = "official"
    FINANCIAL_REPORT = "financial_report"
    RESEARCH_ORG = "research_org"
    NEWS = "news"
    BLOG = "blog"
    UNKNOWN = "unknown"


class WebSearchResult(BaseModel):
    """One normalized result returned by the controlled web search layer."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        str,
        Field(min_length=1, description="Title of the source or web page."),
    ]
    url: Annotated[
        str,
        Field(min_length=1, description="Canonical URL for the search result."),
    ]
    publisher: Annotated[
        str | None,
        Field(description="Organization or author that published the source."),
    ] = None
    published_date: Annotated[
        date | None,
        Field(description="Parsed publication date reported by the source."),
    ] = None
    summary: Annotated[
        str,
        Field(min_length=1, description="Concise summary of the source content."),
    ]
    relevance_score: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description="Search relevance score from 0 (irrelevant) to 1 (most relevant).",
        ),
    ]
    source_quality: Annotated[
        SourceQuality,
        Field(description="Quality category used to prioritize this source."),
    ] = SourceQuality.UNKNOWN
    stale: Annotated[
        bool,
        Field(
            description=(
                "Whether the publication predates the requested recency window."
            )
        ),
    ] = False

    @field_validator("published_date", mode="before")
    @classmethod
    def parse_published_date(cls, value: Any) -> date | None:
        """Normalize provider date strings and datetimes to a calendar date."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise TypeError("published_date must be a date, date string, or None.")

        normalized_value = value.strip()
        if not normalized_value:
            return None
        try:
            return date_parser.parse(normalized_value, fuzzy=False).date()
        except (OverflowError, ValueError) as exc:
            raise ValueError(
                "published_date must contain a recognizable calendar date."
            ) from exc
