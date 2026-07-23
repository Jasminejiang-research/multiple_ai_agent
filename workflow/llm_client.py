"""Single Gemini entry point shared by every workflow node and agent.

Architecture rule (enforced since the Phase 3 ``additional_properties`` 400):
no workflow node or agent may build its own ``genai.Client`` or
``GenerateContentConfig``. Everything goes through ``LLMClient.generate_structured``
so schema-compatibility fixes (see ``workflow.gemini_schema``) live in exactly
one place.
"""

from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from workflow.gemini_schema import relaxed_response_schema

DEFAULT_MODEL_NAME = "gemini-2.5-flash"

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMClient:
    """The only object in this codebase allowed to talk to the Gemini API."""

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """Initialize the shared Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_structured(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        system_instruction: str | None = None,
    ) -> ModelT:
        """Generate output constrained to ``schema`` and strictly validate it.

        Gemini receives the relaxed (constraint-stripped, ref-inlined,
        ``additionalProperties``-free) variant of the schema so the request is
        always accepted; the raw response text is then validated against the
        strict Pydantic model before being returned.

        Args:
            prompt: Full prompt text for the model.
            schema: Strict Pydantic model describing the desired output.
            temperature: Sampling temperature for this call.
            system_instruction: Optional system instruction for the call.

        Returns:
            A validated instance of ``schema``.

        Raises:
            ValueError: If Gemini returns empty text or invalid JSON.
        """
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=relaxed_response_schema(schema),
                temperature=temperature,
            ),
        )

        if not response.text:
            raise ValueError(
                f"Gemini returned an empty response for {schema.__name__}."
            )

        try:
            return schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise ValueError(f"Invalid {schema.__name__} output: {exc}") from exc


class StructuredJsonLLM:
    """Adapter binding ``LLMClient`` to one schema behind ``generate_json``.

    Existing nodes and agents depend on small ``generate_json(prompt) -> str``
    protocols (easy to fake in tests). This adapter keeps those call sites and
    tests unchanged while routing every real call through the shared client.
    """

    def __init__(
        self,
        client: LLMClient,
        schema: type[BaseModel],
        *,
        temperature: float = 0.2,
    ) -> None:
        """Bind a shared client to one output schema and temperature."""
        self._client = client
        self._schema = schema
        self._temperature = temperature

    def generate_json(self, prompt: str) -> str:
        """Return validated JSON text matching the bound schema."""
        result = self._client.generate_structured(
            prompt,
            self._schema,
            temperature=self._temperature,
        )
        return result.model_dump_json()


def create_default_llm_client() -> LLMClient:
    """Create the production ``LLMClient`` from environment configuration."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", DEFAULT_MODEL_NAME)
    return LLMClient(api_key=api_key, model_name=model_name)
