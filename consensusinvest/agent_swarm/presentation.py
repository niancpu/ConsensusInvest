"""Presentation sanitizers for Agent/Judge user-facing text."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")
_URL_RE = re.compile(r"https?://\S+")
_EVIDENCE_ID_RE = re.compile(r"\bev_\d+\b", re.IGNORECASE)
_ARGUMENT_ID_RE = re.compile(r"\barg_\d+\b", re.IGNORECASE)
_TICKER_RE = re.compile(r"\b\d{6}(?:\.[A-Z]{2})?\b")
_MOJIBAKE_HINT_RE = re.compile(r"[\u0080-\u009f\ufffd\u25a1]|[ÃÂâ]|[äåæçéè][\u0080-\u00ff]")


def repair_mojibake_text(value: Any) -> str | None:
    text = _string_value(value)
    if text is None:
        return None
    if not _looks_mojibake(text):
        return text

    candidates = [text]
    for encoding in ("latin-1", "cp1252"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return max(candidates, key=_text_quality_score).strip()


def is_usable_chinese_text(value: Any) -> bool:
    text = repair_mojibake_text(value)
    if text is None:
        return False
    if _looks_mojibake(text):
        return False
    cjk_count = len(_CJK_RE.findall(text))
    if cjk_count == 0:
        return False
    latin_words = _latin_words_for_language_check(text)
    if len(latin_words) <= 2:
        return True
    latin_chars = sum(len(word) for word in latin_words)
    return cjk_count >= 8 and cjk_count >= latin_chars * 0.7


def chinese_text_or_none(value: Any) -> str | None:
    text = repair_mojibake_text(value)
    if text is None or not is_usable_chinese_text(text):
        return None
    return text.strip()


def chinese_sequence(value: Any) -> list[str]:
    return [
        text
        for item in _sequence(value)
        if (text := chinese_text_or_none(item)) is not None
    ]


def sanitize_role_output_for_display(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        cleaned_key = _string_value(key)
        if cleaned_key is None:
            continue
        sanitized_item = _sanitize_role_output_value(item)
        if sanitized_item is not None:
            sanitized[cleaned_key] = sanitized_item
    return sanitized


def display_agent_argument_text(
    *,
    argument: Any,
    agent_id: str,
    role: str,
    round_number: int,
    confidence: float,
    referenced_evidence_ids: Iterable[str],
    counter_evidence_ids: Iterable[str],
) -> str:
    if text := chinese_text_or_none(argument):
        return text
    support_text = _ids_text(referenced_evidence_ids)
    counter_ids = tuple(counter_evidence_ids)
    counter_text = f"；同时将 {_ids_text(counter_ids)} 标为需反驳或复核证据" if counter_ids else ""
    return (
        f"第 {round_number} 轮{agent_role_label(role)}代理论证："
        f"{agent_id} 基于 {support_text} 形成阶段性意见{counter_text}，"
        f"当前置信度为 {confidence:.2f}。"
        "原始论证正文包含英文或乱码，已按中文展示兜底处理；重新运行 workflow 后会生成完整中文论证。"
    )


def display_agent_limitations(limitations: Any) -> list[str]:
    cleaned = chinese_sequence(limitations)
    if cleaned:
        return cleaned
    if _sequence(limitations):
        return ["原始局限说明不是合规中文，需补充同业对比、估值敏感性和最新经营指标验证。"]
    return []


def display_round_summary_text(
    *,
    summary: Any,
    round_number: int,
    agent_argument_ids: Iterable[str],
    referenced_evidence_ids: Iterable[str],
    disputed_evidence_ids: Iterable[str],
) -> str:
    if text := chinese_text_or_none(summary):
        return text
    disputed = tuple(disputed_evidence_ids)
    disputed_text = f"，争议证据包括 {_ids_text(disputed)}" if disputed else ""
    return (
        f"第 {round_number} 轮辩论摘要：本轮汇总了 {_ids_text(agent_argument_ids)} "
        f"等代理论证，引用证据包括 {_ids_text(referenced_evidence_ids)}{disputed_text}。"
        "原始摘要包含英文或乱码，已按中文展示兜底处理。"
    )


def display_judgment_reasoning(
    *,
    reasoning: Any,
    final_signal: str,
    confidence: float,
    positive_evidence_ids: Iterable[str],
    negative_evidence_ids: Iterable[str],
    referenced_agent_argument_ids: Iterable[str],
) -> str:
    if (text := chinese_text_or_none(reasoning)) and not _is_generic_judgment_reasoning(text):
        return text
    return (
        f"最终判断为{final_signal_label(final_signal)}，置信度 {confidence:.2f}。"
        f"判断引用代理论证 {_ids_text(referenced_agent_argument_ids)}，"
        f"关键正向证据 {_ids_text(positive_evidence_ids)}，"
        f"关键负向证据 {_ids_text(negative_evidence_ids)}。"
        "原始判断说明包含英文或乱码，已按中文展示兜底处理。"
    )


def display_chinese_notes(value: Any, *, fallback: str | None = None) -> list[str]:
    cleaned = chinese_sequence(value)
    if cleaned:
        return cleaned
    return [fallback] if fallback and _sequence(value) else []


def _is_generic_judgment_reasoning(text: str) -> bool:
    generic_phrases = (
        "基于已保存智能体论证和关键证据形成判断",
        "基于已保存轮次摘要、智能体论证和关键证据",
    )
    return any(phrase in text for phrase in generic_phrases)


def agent_role_label(role: str) -> str:
    labels = {
        "bullish_interpreter": "多头解释",
        "bearish_interpreter": "空头复核",
        "neutral_reviewer": "中性复核",
        "risk_reviewer": "风险复核",
    }
    return labels.get(role, role)


def final_signal_label(value: str) -> str:
    return {
        "bullish": "偏多",
        "neutral": "中性",
        "bearish": "偏空",
        "insufficient_evidence": "证据不足",
    }.get(value, value)


def _sanitize_role_output_value(value: Any) -> Any | None:
    if isinstance(value, str):
        return chinese_text_or_none(value)
    if isinstance(value, Mapping):
        nested = sanitize_role_output_for_display(value)
        return nested or None
    if isinstance(value, (list, tuple, set)):
        items = [
            sanitized
            for item in value
            if (sanitized := _sanitize_role_output_value(item)) is not None
        ]
        return items or None
    return value


def _latin_words_for_language_check(text: str) -> list[str]:
    stripped = _URL_RE.sub(" ", text)
    stripped = _EVIDENCE_ID_RE.sub(" ", stripped)
    stripped = _ARGUMENT_ID_RE.sub(" ", stripped)
    stripped = _TICKER_RE.sub(" ", stripped)
    return [
        word
        for word in _LATIN_WORD_RE.findall(stripped)
        if word.lower() not in {"workflow", "id", "url"}
    ]


def _looks_mojibake(text: str) -> bool:
    return bool(_MOJIBAKE_HINT_RE.search(text))


def _text_quality_score(text: str) -> tuple[int, int, int]:
    return (
        len(_CJK_RE.findall(text)),
        -len(_MOJIBAKE_HINT_RE.findall(text)),
        -len(_latin_words_for_language_check(text)),
    )


def _ids_text(values: Iterable[str]) -> str:
    ids = [str(value) for value in values if str(value).strip()]
    return "、".join(ids) if ids else "暂无明确 ID"


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
