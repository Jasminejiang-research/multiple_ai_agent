"""LLM adapters used by deterministic workflow nodes."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.workflow import CritiqueReport, ProposalOutline, SectionDrafts

MODEL_NAME = "gemini-2.5-flash"


class GeminiPlannerLLM:
    """Gemini-backed JSON generator for the ProposalPlanner node."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``ProposalOutline`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ProposalOutline,
                temperature=0.2,
            ),
        )

        if response.parsed is not None:
            if isinstance(response.parsed, ProposalOutline):
                return response.parsed.model_dump_json()
            return ProposalOutline.model_validate(response.parsed).model_dump_json()

        if not response.text:
            raise ValueError("Gemini returned an empty planner response.")

        return response.text


class GeminiSectionWriterLLM:
    """Gemini-backed JSON generator for the SectionWriter node."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``SectionDrafts`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SectionDrafts,
                temperature=0.3,
            ),
        )

        if response.parsed is not None:
            if isinstance(response.parsed, SectionDrafts):
                return response.parsed.model_dump_json()
            return SectionDrafts.model_validate(response.parsed).model_dump_json()

        if not response.text:
            raise ValueError("Gemini returned an empty section writer response.")

        return response.text


class GeminiBasicCriticLLM:
    """Gemini-backed JSON generator for the BasicCritic node."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``CritiqueReport`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CritiqueReport,
                temperature=0.2,
            ),
        )

        if response.parsed is not None:
            if isinstance(response.parsed, CritiqueReport):
                return response.parsed.model_dump_json()
            return CritiqueReport.model_validate(response.parsed).model_dump_json()

        if not response.text:
            raise ValueError("Gemini returned an empty basic critic response.")

        return response.text


def create_default_planner_llm() -> GeminiPlannerLLM:
    """Create the default production LLM adapter for the planner node."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiPlannerLLM(api_key=api_key, model_name=model_name)


def create_default_section_writer_llm() -> GeminiSectionWriterLLM:
    """Create the default production LLM adapter for the SectionWriter node."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiSectionWriterLLM(api_key=api_key, model_name=model_name)


def create_default_basic_critic_llm() -> GeminiBasicCriticLLM:
    """Create the default production LLM adapter for the BasicCritic node."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiBasicCriticLLM(api_key=api_key, model_name=model_name)
