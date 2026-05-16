"""LLM provider adapters for Agent Swarm and Judge Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import ast
import codecs
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
    base_url: str | None = None
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
            base_url=_llm_base_url_from_env(),
            temperature=_env_float("CONSENSUSINVEST_LLM_TEMPERATURE", 0.2),
            timeout_seconds=_env_float("CONSENSUSINVEST_LLM_TIMEOUT_SECONDS", 60.0),
        )

    def model_for(self, purpose: str) -> str:
        if purpose.startswith("judge") and self.judge_model:
            return self.judge_model
        if purpose.startswith(("agent", "round")) and self.swarm_model:
            return self.swarm_model
        return self.model

    def missing_credential_env_groups(self) -> tuple[tuple[str, ...], ...]:
        groups: list[tuple[str, ...]] = []
        for model in (self.model, self.swarm_model, self.judge_model):
            if model:
                groups.extend(_credential_env_groups_for_model(model))
        return tuple(
            group
            for group in _unique_groups(groups)
            if not any(os.environ.get(name, "").strip() for name in group)
        )

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

        selected_model = model or self.model_for(purpose)
        api_key = _api_key_for_model(selected_model)
        if _credential_env_groups_for_model(selected_model) and not api_key:
            raise RuntimeError(
                "llm_missing_credentials: no API key is available for "
                f"model {selected_model}"
            )
        try:
            response = completion(
                model=selected_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
                temperature=self.temperature,
                timeout=self.timeout_seconds,
                base_url=self.base_url,
                api_key=api_key,
                stream=False,
            )
        except Exception as exc:
            content = _message_content_from_exception(exc)
            if content is None:
                raise
            return _parse_json_object(content)
        content = _message_content(response)
        return _parse_json_object(content)


def build_agent_llm_provider_from_env() -> AgentLLMProvider:
    return LiteLLMAgentProvider.from_env()


def _message_content(response: Any) -> str:
    if isinstance(response, str):
        content = _message_content_from_sse(response) or response
        if content.strip():
            return content.strip()
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


def _message_content_from_exception(exc: Exception) -> str | None:
    text = str(exc)
    direct_sse = _message_content_from_sse(_extract_sse_text(text))
    if direct_sse is not None:
        return direct_sse
    marker = "Received:"
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    received_text = text[marker_index + len(marker) :].strip()
    if received_text.startswith(("'", '"')):
        try:
            received_value = ast.literal_eval(received_text)
        except (SyntaxError, ValueError):
            received_value = _trim_received_literal(received_text)
    else:
        received_value = received_text
    if not isinstance(received_value, str):
        return None
    return _message_content_from_sse(received_value)


def _extract_sse_text(text: str) -> str:
    start = text.find("data:")
    if start < 0:
        return text
    end_marker = "data: [DONE]"
    end = text.find(end_marker, start)
    if end >= 0:
        end += len(end_marker)
        return text[start:end]
    return text[start:]


def _trim_received_literal(text: str) -> str:
    quote = text[0]
    end = text.rfind(quote)
    if end > 0:
        return text[1:end]
    return text


def _message_content_from_sse(text: str) -> str | None:
    chunks: list[str] = []
    for raw_line in _sse_lines(text):
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            continue
        payload = _loads_sse_json(data)
        if payload is None:
            continue
        choices = payload.get("choices") if isinstance(payload, Mapping) else None
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            delta = choice.get("delta")
            if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
                chunks.append(delta["content"])
                continue
            message = choice.get("message")
            if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                chunks.append(message["content"])
    content = "".join(chunks).strip()
    return content or None


def _sse_lines(text: str) -> list[str]:
    if "\n" in text:
        return text.splitlines()
    return text.replace("\\n\\n", "\n\n").splitlines()


def _loads_sse_json(data: str) -> Any | None:
    for candidate in (data, _unicode_unescape(data)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _unicode_unescape(value: str) -> str:
    try:
        return codecs.decode(value, "unicode_escape")
    except UnicodeDecodeError:
        return value


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    candidates = [text]
    decoded_text = _unicode_unescape(text)
    if decoded_text != text:
        candidates.append(decoded_text)
    first_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            break
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                parsed = json.loads(candidate[start : end + 1])
                break
            except json.JSONDecodeError as nested_exc:
                first_error = first_error or nested_exc
    else:
        raise RuntimeError("llm_invalid_json") from first_error
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


def _llm_base_url_from_env() -> str | None:
    for name in (
        "CONSENSUSINVEST_LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_BASE",
        "GEMINI_API_BASE",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _credential_env_groups_for_model(model: str) -> tuple[tuple[str, ...], ...]:
    normalized = model.strip().lower()
    if normalized.startswith(("openai/", "oai/")):
        return (("OPENAI_API_KEY",),)
    if normalized.startswith("anthropic/"):
        return (("ANTHROPIC_API_KEY",),)
    if normalized.startswith(("gemini/", "google/")):
        return (("GEMINI_API_KEY", "GOOGLE_API_KEY"),)
    if normalized.startswith("deepseek/"):
        return (("DEEPSEEK_API_KEY",),)
    if normalized.startswith("openrouter/"):
        return (("OPENROUTER_API_KEY",),)
    if normalized.startswith("dashscope/"):
        return (("DASHSCOPE_API_KEY",),)
    if normalized.startswith("azure/"):
        return (("AZURE_API_KEY", "AZURE_OPENAI_API_KEY"),)
    return ()


def _api_key_for_model(model: str) -> str | None:
    for group in _credential_env_groups_for_model(model):
        for name in group:
            value = os.environ.get(name, "").strip()
            if value:
                return value
    return None


def _unique_groups(groups: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    result: list[tuple[str, ...]] = []
    for group in groups:
        if group in seen:
            continue
        seen.add(group)
        result.append(group)
    return result


__all__ = [
    "AgentLLMProvider",
    "LiteLLMAgentProvider",
    "build_agent_llm_provider_from_env",
]
