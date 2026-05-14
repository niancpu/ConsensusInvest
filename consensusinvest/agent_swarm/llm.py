"""LLM provider adapters for Agent Swarm and Judge Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from typing import Any, Protocol


class AgentLLMProvider(Protocol):
    def complete_json(
        self,
        *,
        purpose: str,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class LiteLLMAgentProvider:
    model: str
    swarm_model: str | None = None
    judge_model: str | None = None
    temperature: float = 0.2
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> LiteLLMAgentProvider:
        provider = os.environ.get("CONSENSUSINVEST_LLM_PROVIDER", "").strip().lower()
        if not provider:
            raise RuntimeError(
                "CONSENSUSINVEST_LLM_PROVIDER is required; set it to 'litellm' for real Agent runtime"
            )
        if provider not in {"litellm", "lite_llm"}:
            raise RuntimeError(f"unsupported CONSENSUSINVEST_LLM_PROVIDER: {provider}")
        model = os.environ.get("CONSENSUSINVEST_LLM_MODEL", "").strip()
        swarm_model = os.environ.get("CONSENSUSINVEST_SWARM_MODEL", "").strip() or None
        judge_model = os.environ.get("CONSENSUSINVEST_JUDGE_MODEL", "").strip() or None
        if not model and not swarm_model and not judge_model:
            raise RuntimeError(
                "CONSENSUSINVEST_LLM_PROVIDER=litellm requires CONSENSUSINVEST_LLM_MODEL "
                "or a runtime-specific model"
            )
        return cls(
            model=model or swarm_model or judge_model or "",
            swarm_model=swarm_model,
            judge_model=judge_model,
            temperature=_env_float("CONSENSUSINVEST_LLM_TEMPERATURE", 0.2),
            timeout_seconds=_env_float("CONSENSUSINVEST_LLM_TIMEOUT_SECONDS", 60.0),
        )

    def model_for(self, purpose: str) -> str:
        if purpose.startswith("judge") and self.judge_model:
            return self.judge_model
        if purpose.startswith(("agent", "round")) and self.swarm_model:
            return self.swarm_model
        return self.model

    def complete_json(
        self,
        *,
        purpose: str,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        try:
            from litellm import completion
        except ModuleNotFoundError as exc:
            raise RuntimeError("litellm is required for real Agent LLM runtime") from exc

        response = completion(
            model=model or self.model_for(purpose),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            temperature=self.temperature,
            timeout=self.timeout_seconds,
        )
        content = _message_content(response)
        return _parse_json_object(content)


def build_agent_llm_provider_from_env() -> AgentLLMProvider:
    return LiteLLMAgentProvider.from_env()


def _message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        content = None
    if content is None and isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
            if isinstance(message, Mapping):
                content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("llm_empty_response")
    return content.strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("llm_invalid_json") from exc
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as nested_exc:
            raise RuntimeError("llm_invalid_json") from nested_exc
    if not isinstance(parsed, dict):
        raise RuntimeError("llm_response_must_be_object")
    return parsed


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


__all__ = [
    "AgentLLMProvider",
    "LiteLLMAgentProvider",
    "build_agent_llm_provider_from_env",
]
