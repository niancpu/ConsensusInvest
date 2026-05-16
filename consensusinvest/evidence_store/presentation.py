"""Presentation helpers for Evidence text derived from structured provider rows."""

from __future__ import annotations

import json
import math
import re
from typing import Any


_NUMERIC_TOKEN_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_INFORMATIVE_CHAR_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_FORBIDDEN_PRESENTATION_KEYS = {
    "action",
    "bearish",
    "bullish",
    "buy",
    "hold",
    "investment_action",
    "net_impact",
    "recommendation",
    "sell",
    "suggested_action",
    "trade_signal",
    "trading_signal",
}


def display_text_for_raw_payload(
    current_text: str | None,
    raw_payload: dict[str, Any] | None,
    *,
    source_label: str | None = None,
) -> str | None:
    """Return a readable text projection when legacy Evidence text is not useful."""

    if not needs_text_repair(current_text):
        return current_text
    summary = provider_record_summary(raw_payload, source_label=source_label)
    return summary or current_text


def provider_record_summary(
    raw_payload: dict[str, Any] | None,
    *,
    source_label: str | None = None,
) -> str | None:
    if not raw_payload:
        return None
    provider_response = _as_mapping(raw_payload.get("provider_response"))
    record = provider_response or _as_mapping(raw_payload)
    if not record:
        return None

    label = source_label or _source_label(raw_payload)
    pairs = [
        (str(key), value)
        for key, value in record.items()
        if _include_key(str(key), value)
    ]
    if not pairs:
        return f"{label} 返回了结构化表格行，但没有可展示的正文。"

    labeled = "；".join(f"{key}：{_format_value(value)}" for key, value in pairs[:12])
    if _mostly_numeric_values([value for _, value in pairs]):
        return f"{label} 结构化行情/财务数据：{labeled}"
    return f"{label} 结构化数据：{labeled}"


def needs_text_repair(value: str | None) -> bool:
    if value is None:
        return True
    text = " ".join(str(value).split())
    if not text or text == "No objective source text available.":
        return True
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        return True
    numeric_tokens = _NUMERIC_TOKEN_RE.findall(text)
    if len(numeric_tokens) < 4:
        return False
    numeric_chars = sum(len(token) for token in numeric_tokens)
    informative_chars = len(_INFORMATIVE_CHAR_RE.findall(_NUMERIC_TOKEN_RE.sub("", text)))
    return numeric_chars >= max(18, informative_chars * 2)


def _source_label(raw_payload: dict[str, Any]) -> str:
    source = str(raw_payload.get("provider_api") or "").strip()
    if source:
        if "akshare" in source.lower():
            return "AkShare"
        if "tushare" in source.lower():
            return "TuShare"
    return "数据源"


def _include_key(key: str, value: Any) -> bool:
    normalized = key.strip().lower()
    return (
        bool(normalized)
        and not normalized.startswith("_")
        and normalized not in _FORBIDDEN_PRESENTATION_KEYS
        and value not in (None, "")
    )


def _mostly_numeric_values(values: list[Any]) -> bool:
    if not values:
        return False
    numeric = sum(1 for value in values if isinstance(value, int | float) and not isinstance(value, bool))
    return numeric >= max(2, math.ceil(len(values) * 0.5))


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _as_mapping(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None
