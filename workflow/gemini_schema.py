"""Build constraint-light JSON schemas for Gemini structured output.

Gemini compiles ``response_schema`` into a constrained-decoding state machine
with a hard cap on the number of states it will serve. Length, pattern, item
count, and numeric-bound constraints multiply that state count and trigger a
``400 INVALID_ARGUMENT`` ("schema produces a constraint that has too many
states for serving") for our nested 13-section workflow schemas.

The fix is to decouple the *generation* schema from the *validation* schema:
we send Gemini a structurally identical but constraint-stripped schema so the
grammar stays small, then validate the returned JSON against the strict
Pydantic model as usual. Strict Pydantic validation is preserved; only the
decoding-time constraints are dropped.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Keys that inflate the constrained-decoding state machine or that the Gemini
# Schema proto does not know at all. ``additionalProperties`` is emitted by
# Pydantic for every ``extra="forbid"`` model and triggers a 400
# ``Unknown name "additional_properties"`` from the API. They are all still
# enforced by Pydantic when the response text is validated after generation, so
# stripping them here does not weaken output validation.
_CONSTRAINT_KEYS: frozenset[str] = frozenset(
    {
        "additionalProperties",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)

# A large enum (many members, or long member names) is the dominant "too many
# states for serving" trigger, especially when the same enum is repeated across
# many nested objects (e.g. the 13-value section ``title`` in every section).
# When an enum crosses either threshold we drop it from the *generation* schema
# and keep the plain type; the prompt already lists the allowed values and the
# strict Pydantic model still validates them after generation.
_MAX_ENUM_MEMBERS = 6
_MAX_ENUM_TOTAL_CHARS = 100


def _is_expensive_enum(values: list[Any]) -> bool:
    """Return True when an enum is large enough to risk the serving limit."""
    if len(values) > _MAX_ENUM_MEMBERS:
        return True
    total_chars = sum(len(str(value)) for value in values)
    return total_chars > _MAX_ENUM_TOTAL_CHARS


def _infer_enum_type(values: list[Any]) -> str:
    """Infer a JSON-schema ``type`` for an enum we are about to drop."""
    if values and all(isinstance(value, bool) for value in values):
        return "boolean"
    if values and all(isinstance(value, int) for value in values):
        return "integer"
    if values and all(isinstance(value, (int, float)) for value in values):
        return "number"
    return "string"


def _clean(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively strip constraints and inline ``$ref`` targets.

    Args:
        node: A JSON-schema fragment (dict, list, or scalar).
        defs: The top-level ``$defs`` map used to resolve ``$ref`` pointers.

    Returns:
        A constraint-free, ref-free copy of ``node``.
    """
    if isinstance(node, dict):
        # Resolve a ``$ref`` by inlining its (cleaned) target, then merging any
        # sibling keywords (e.g. a field-level ``description``) over it.
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            resolved = _clean(defs.get(ref_name, {}), defs)
            if isinstance(resolved, dict):
                for key, value in node.items():
                    if key == "$ref" or key in _CONSTRAINT_KEYS or key == "$defs":
                        continue
                    resolved.setdefault(key, _clean(value, defs))
            return resolved

        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _CONSTRAINT_KEYS or key == "$defs":
                continue
            cleaned[key] = _clean(value, defs)

        # Flatten a single-element ``allOf`` (Pydantic wraps referenced
        # submodels this way); Gemini handles a flat object more reliably.
        all_of = cleaned.get("allOf")
        if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
            merged = cleaned.pop("allOf")[0]
            for key, value in merged.items():
                cleaned.setdefault(key, value)

        # Collapse expensive enums to their plain type to stay within Gemini's
        # serving limit. Small enums (e.g. confidence/severity) are kept as
        # generation hints; strict Pydantic still validates every value.
        enum_values = cleaned.get("enum")
        if isinstance(enum_values, list) and _is_expensive_enum(enum_values):
            cleaned.pop("enum")
            cleaned.setdefault("type", _infer_enum_type(enum_values))

        return cleaned

    if isinstance(node, list):
        return [_clean(item, defs) for item in node]

    return node


def relaxed_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a constraint-stripped, ref-inlined schema dict for Gemini.

    The returned dict keeps the full structure (properties, types, nesting, and
    enums) of ``model`` but drops the constraint keywords that cause Gemini's
    "too many states for serving" error. Callers must still validate the model
    output with ``model.model_validate_json(...)`` to enforce the constraints.

    Args:
        model: The strict Pydantic model describing the desired output.

    Returns:
        A plain JSON-schema dict safe to pass as ``response_schema``.
    """
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    return _clean(schema, defs)
