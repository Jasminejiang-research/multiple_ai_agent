"""Enum contract text for prompts, mirroring the shared list-size contract.

``workflow.llm_client.schema_cardinality_contract`` lifts list-size limits out
of a Pydantic schema and restates them as explicit prompt text, because a model
follows a short imperative rule more reliably than a constraint buried in a
JSON schema. Enums had no equivalent, and a 3B model reliably invents
``claim_type`` values -- pattern-matching them to the surrounding section name
(``business_model`` -> ``business_model_logic``) -- even when the schema and a
correction request both list the nine allowed values.

This module is the enum counterpart. It only adds prompt text: model output is
never rewritten, so the SLM arm stays comparable with the Gemini arm.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

MAX_TRAVERSAL_DEPTH = 16
# Beyond this, restating every member costs more prompt than it buys.
MAX_CONTRACT_MEMBERS = 24


def _resolve_local_ref(
    root_schema: Mapping[str, Any],
    reference: str,
) -> Mapping[str, Any] | None:
    """Resolve a local JSON Schema reference such as ``#/$defs/Model``."""
    if not reference.startswith("#/"):
        return None
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, Mapping) else None


def _collect_enums(
    fragment: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: tuple[str, ...],
    output: list[tuple[str, tuple[str, ...]]],
    *,
    depth: int = 0,
    seen_refs: frozenset[str] = frozenset(),
) -> None:
    """Collect ``enum`` and single-value ``const`` members with field paths."""
    if depth > MAX_TRAVERSAL_DEPTH:
        return

    reference = fragment.get("$ref")
    if isinstance(reference, str):
        # Recursive models would otherwise loop forever.
        if reference in seen_refs:
            return
        resolved = _resolve_local_ref(root_schema, reference)
        if resolved is not None:
            _collect_enums(
                resolved,
                root_schema,
                path,
                output,
                depth=depth + 1,
                seen_refs=seen_refs | {reference},
            )
        return

    enum_values = fragment.get("enum")
    if path and isinstance(enum_values, list) and enum_values:
        output.append(
            (".".join(path), tuple(str(value) for value in enum_values))
        )

    items = fragment.get("items")
    if isinstance(items, Mapping):
        item_path = (*path[:-1], f"{path[-1]}[]") if path else ("[]",)
        _collect_enums(
            items,
            root_schema,
            item_path,
            output,
            depth=depth + 1,
            seen_refs=seen_refs,
        )

    properties = fragment.get("properties")
    if isinstance(properties, Mapping):
        for field_name, field_schema in properties.items():
            if isinstance(field_schema, Mapping):
                _collect_enums(
                    field_schema,
                    root_schema,
                    (*path, str(field_name)),
                    output,
                    depth=depth + 1,
                    seen_refs=seen_refs,
                )

    for union_key in ("anyOf", "oneOf", "allOf"):
        alternatives = fragment.get(union_key)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, Mapping):
                    _collect_enums(
                        alternative,
                        root_schema,
                        path,
                        output,
                        depth=depth + 1,
                        seen_refs=seen_refs,
                    )


def schema_enum_contract(schema: type[BaseModel]) -> str:
    """Restate a schema's enum members as explicit prompt instructions.

    Mirrors the grouping of the shared list-size contract: a field name that
    appears with identical members in three or more places collapses to one
    ``*.field`` line, so a 13-section schema does not repeat the same enum
    thirteen times.

    Returns an empty string when the schema declares no enums.
    """
    root_schema = schema.model_json_schema()
    collected: list[tuple[str, tuple[str, ...]]] = []
    _collect_enums(root_schema, root_schema, (), collected)

    unique_enums = sorted(set(collected))
    grouped: defaultdict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(
        list
    )
    for path, members in unique_enums:
        grouped[(path.rsplit(".", 1)[-1], members)].append(path)

    instructions: list[str] = []
    emitted: set[tuple[str, tuple[str, ...]]] = set()
    for path, members in unique_enums:
        if len(members) > MAX_CONTRACT_MEMBERS:
            continue
        leaf = path.rsplit(".", 1)[-1]
        group_key = (leaf, members)
        grouped_paths = grouped[group_key]
        if len(grouped_paths) >= 3:
            if group_key in emitted:
                continue
            emitted.add(group_key)
            display_path = f"*.{leaf} ({len(grouped_paths)} fields)"
        else:
            display_path = path
        allowed = ", ".join(f'"{member}"' for member in members)
        instructions.append(f"- `{display_path}`: exactly one of {allowed}.")

    if not instructions:
        return ""
    return (
        "# Schema Enum Contract (generated automatically)\n\n"
        + "\n".join(instructions)
        + "\n\nThese lists are closed. Never invent a value that describes the "
        "surrounding section or field name; pick the closest listed member, or "
        '"general" when one is offered and nothing else fits.'
    )


__all__ = ["schema_enum_contract"]
