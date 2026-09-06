"""Tests for the SLM-only enum contract appended to prompts."""

from __future__ import annotations

from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field

from schemas.workflow import ProposalDraft
from slm.schema_contract import MAX_CONTRACT_MEMBERS, schema_enum_contract


class _NoEnums(BaseModel):
    name: str
    count: int


class _OneEnum(BaseModel):
    status: Literal["open", "closed"]


class _Nested(BaseModel):
    confidence: Literal["high", "medium", "low"]


class _RepeatedEnums(BaseModel):
    first: _Nested
    second: _Nested
    third: _Nested


class _InList(BaseModel):
    entries: Annotated[list[_Nested], Field(max_length=4)]


class _Recursive(BaseModel):
    label: Literal["a", "b"]
    child: "_Recursive | None" = None


def test_schema_without_enums_produces_no_contract() -> None:
    assert schema_enum_contract(_NoEnums) == ""


def test_single_enum_is_listed_with_its_full_path() -> None:
    contract = schema_enum_contract(_OneEnum)

    assert "# Schema Enum Contract (generated automatically)" in contract
    assert '- `status`: exactly one of "open", "closed".' in contract


def test_repeated_enum_collapses_to_one_grouped_line() -> None:
    """A 13-section schema must not repeat the same enum thirteen times."""
    contract = schema_enum_contract(_RepeatedEnums)

    assert contract.count("confidence") == 1
    assert '`*.confidence (3 fields)`' in contract
    assert '"high", "medium", "low"' in contract


def test_enum_inside_a_list_is_found() -> None:
    contract = schema_enum_contract(_InList)

    assert "entries[].confidence" in contract


def test_recursive_schema_terminates() -> None:
    contract = schema_enum_contract(_Recursive)

    assert '"a", "b"' in contract


def test_oversized_enum_is_skipped() -> None:
    many_members = tuple(f"value_{index}" for index in range(MAX_CONTRACT_MEMBERS + 1))

    class _Huge(BaseModel):
        kind: Literal[many_members]  # type: ignore[valid-type]

    assert schema_enum_contract(_Huge) == ""


def test_proposal_draft_contract_covers_the_invented_field() -> None:
    """claim_type is the enum the writer kept inventing values for."""
    contract = schema_enum_contract(ProposalDraft)

    assert "claim_type" in contract
    for member in (
        "market_size",
        "competitor",
        "trend",
        "financial_benchmark",
        "customer",
        "product",
        "operational",
        "regulatory",
        "general",
    ):
        assert f'"{member}"' in contract
    # Compact enough to append to every request.
    assert len(contract) < 1_500


@pytest.mark.parametrize("schema", [_NoEnums, _OneEnum, _RepeatedEnums, ProposalDraft])
def test_contract_is_deterministic(schema: type[BaseModel]) -> None:
    assert schema_enum_contract(schema) == schema_enum_contract(schema)
