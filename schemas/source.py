"""Schemas for controlled web research results."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


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
        str | None,
        Field(description="Publication date as reported by the source."),
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
