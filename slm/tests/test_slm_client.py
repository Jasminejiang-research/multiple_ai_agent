"""Contract tests for the isolated SLM client skeleton."""

from __future__ import annotations

import workflow.llm_client as shared_llm_client

import slm.client as client_module
from slm.client import SLMClient
from slm.config import SLMConfig


def _config() -> SLMConfig:
    return SLMConfig(
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:3b",
        api_key="ollama",
        structured_mode="json_schema",
        max_prompt_chars=60_000,
        max_output_tokens=8_192,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=300,
    )


def test_slm_client_initializes_openai_compatible_sdk(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sdk_client = object()

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return sdk_client

    monkeypatch.setattr(client_module.openai, "OpenAI", fake_openai)

    client = SLMClient(_config())

    assert captured == {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "timeout": 300,
    }
    assert client._client is sdk_client
    assert client._model_name == "qwen2.5:3b"
    assert client._structured_mode == "json_schema"
    assert client._max_prompt_chars == 60_000
    assert client._max_output_tokens == 8_192


def test_shared_usage_tracker_private_contract() -> None:
    assert hasattr(shared_llm_client, "_ACTIVE_USAGE_TRACKER")
    assert (
        client_module._ACTIVE_USAGE_TRACKER
        is shared_llm_client._ACTIVE_USAGE_TRACKER
    )
