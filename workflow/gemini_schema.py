"""Build structure-only JSON schemas for Gemini structured output.

Gemini compiles ``response_schema`` into a constrained-decoding state machine
with a hard cap on the number of states it will serve. Constraints, annotations,
and enums multiply that state count and trigger a ``400 INVALID_ARGUMENT``
("schema produces a constraint that has too many states for serving") for our
nested 13-section workflow schemas.

The fix is to decouple the *generation* schema from the *validation* schema:
the generation schema retains only structure (``type``, ``properties``,
``required``, ``items``, and structural composition), while annotations and
enums are stripped. Semantic constraints are carried by both the prompt
contract and strict local Pydantic validation.
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

# Schema annotations add request text and do not constrain the JSON shape.
# ``title`` and ``description`` may also be *business property names*, so these
# keys are stripped only at a schema-fragment level. The ``properties`` mapping
# is handled specially by ``_clean`` to preserve every business field name.
_ANNOTATION_KEYS: frozenset[str] = frozenset(
    {"description", "title", "examples", "default", "$comment"}
)


def _is_expensive_enum(values: list[Any]) -> bool:
    """Return True because every enum inflates Gemini's serving state count."""
    return True


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
        # cleaned sibling structural keywords over it.
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            resolved = _clean(defs.get(ref_name, {}), defs)
            if isinstance(resolved, dict):
                siblings = _clean(
                    {key: value for key, value in node.items() if key != "$ref"},
                    defs,
                )
                if isinstance(siblings, dict):
                    for key, value in siblings.items():
                        resolved.setdefault(key, value)
            return resolved

        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _CONSTRAINT_KEYS or key in _ANNOTATION_KEYS or key == "$defs":
                continue
            if key == "properties" and isinstance(value, dict):
                cleaned[key] = {
                    property_name: _clean(property_schema, defs)
                    for property_name, property_schema in value.items()
                }
            else:
                cleaned[key] = _clean(value, defs)

        # Flatten a single-element ``allOf`` (Pydantic wraps referenced
        # submodels this way); Gemini handles a flat object more reliably.
        all_of = cleaned.get("allOf")
        if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
            merged = cleaned.pop("allOf")[0]
            for key, value in merged.items():
                cleaned.setdefault(key, value)

        # Collapse every enum to its plain type. Even small enums become state
        # multipliers when repeated across the nested 13-section schema.
        enum_values = cleaned.get("enum")
        if isinstance(enum_values, list) and _is_expensive_enum(enum_values):
            cleaned.pop("enum")
            cleaned.setdefault("type", _infer_enum_type(enum_values))

        return cleaned

    if isinstance(node, list):
        return [_clean(item, defs) for item in node]

    return node


def relaxed_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a structure-only, ref-inlined schema dict for Gemini.

    The generation schema retains structure (types, properties, required fields,
    items, and nesting) but drops annotations, enums, and other constraints that
    cause Gemini's "too many states for serving" error. The prompt contract
    communicates semantic constraints to the model, and callers must validate
    output with ``model.model_validate_json(...)`` to enforce them locally.

    Args:
        model: The strict Pydantic model describing the desired output.

    Returns:
        A plain JSON-schema dict safe to pass as ``response_schema``.
    """
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    return _clean(schema, defs)
