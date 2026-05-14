"""Deterministic Evidence Normalizer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, TypeVar

from consensusinvest.runtime import InternalCallEnvelope

from .models import (
    EvidenceItemDraft,
    EvidenceNormalizationResult,
    NormalizedSearchResult,
    NormalizedEvidenceDraft,
    RawItemDraft,
)

_T = TypeVar("_T")

FORBIDDEN_FACT_FIELDS = {
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


class EvidenceNormalizer:
    """Normalizes SearchResultPackage items into Raw/Evidence drafts.

    The normalizer is deliberately deterministic. It standardizes identifiers,
    timestamps, source metadata, quality dimensions, and dedupe keys; it does
    not infer investment direction or write durable state.
    """

    def normalize_search_result(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> EvidenceNormalizationResult:
        from consensusinvest.evidence_store.models import IngestRejectedItem

        drafts: list[NormalizedEvidenceDraft] = []
        rejected_items: list[IngestRejectedItem] = []
        for item in _iter_package_items(package):
            normalized = self.normalize_item(envelope, package, item)
            if isinstance(normalized, IngestRejectedItem):
                rejected_items.append(normalized)
            else:
                drafts.append(normalized)
        return EvidenceNormalizationResult(drafts=drafts, rejected_items=rejected_items)

    def normalize_package(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> EvidenceNormalizationResult:
        return self.normalize_search_result(envelope, package)

    def normalize_search_result_package(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> NormalizedSearchResult:
        result = self.normalize_search_result(envelope, package)
        from consensusinvest.evidence_store.models import EvidenceItem, RawItem

        raw_items: list[RawItem] = []
        evidence_items: list[EvidenceItem] = []
        task_id = _clean_key_value(_value(package, "task_id"))
        for index, draft in enumerate(result.drafts, start=1):
            raw_ref = f"raw_{index:06d}"
            evidence_id = f"ev_{index:06d}"
            raw = RawItem(
                raw_ref=raw_ref,
                source=draft.raw.source,
                source_type=draft.raw.source_type,
                ticker=draft.raw.ticker,
                entity_ids=draft.raw.entity_ids,
                title=draft.raw.title,
                content=draft.raw.content,
                content_preview=draft.raw.content_preview,
                url=draft.raw.url,
                publish_time=draft.raw.publish_time,
                fetched_at=draft.raw.fetched_at,
                author=draft.raw.author,
                language=draft.raw.language,
                raw_payload=dict(draft.raw.raw_payload),
                ingest_context=ingest_context(envelope, task_id=task_id),
            )
            evidence = EvidenceItem(
                evidence_id=evidence_id,
                raw_ref=raw_ref,
                ticker=draft.evidence.ticker,
                entity_ids=draft.evidence.entity_ids,
                source=draft.evidence.source,
                source_type=draft.evidence.source_type,
                evidence_type=draft.evidence.evidence_type,
                title=draft.evidence.title,
                content=draft.evidence.content,
                url=draft.evidence.url,
                publish_time=draft.evidence.publish_time,
                fetched_at=draft.evidence.fetched_at,
                source_quality=draft.evidence.source_quality,
                relevance=draft.evidence.relevance,
                freshness=draft.evidence.freshness,
                quality_notes=draft.evidence.quality_notes,
            )
            raw_items.append(raw)
            evidence_items.append(evidence)

        return NormalizedSearchResult(
            status=_normalization_status(raw_items, result.rejected_items),
            raw_items=raw_items,
            evidence_items=evidence_items,
            rejected_items=result.rejected_items,
        )

    def normalize_item(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
        item: Any,
    ) -> NormalizedEvidenceDraft | IngestRejectedItem:
        data = _to_mapping(item)
        from consensusinvest.evidence_store.models import IngestRejectedItem

        external_id = _clean_key_value(data.get("external_id"))

        violation_path = find_forbidden_fact_key(
            data,
            skip_keys={"raw_payload", "provider_response"},
        )
        if violation_path is not None:
            return _rejected(
                external_id,
                "write_boundary_violation",
                f"directional field is not allowed in Evidence: {violation_path}",
            )

        raw_publish_time = data.get("publish_time") or data.get("published_at")
        publish_time = parse_datetime(raw_publish_time)
        if raw_publish_time and publish_time is None:
            return _rejected(
                external_id,
                "invalid_request",
                "publish_time must be an ISO datetime when provided",
            )
        if datetime_after(publish_time, envelope.analysis_time):
            return _rejected(
                external_id,
                "publish_time_after_analysis_time",
                "item publish_time is later than envelope.analysis_time",
            )

        primary_key = _item_dedupe_key(data, package)
        if primary_key is None:
            return _rejected(
                external_id,
                "invalid_request",
                "search result item must include url or external_id",
            )

        source = _item_source(data, package)
        source_type = _clean_key_value(data.get("source_type")) or _clean_key_value(
            _value(package, "source_type")
        )
        target = _value(package, "target")
        ticker = _clean_key_value(data.get("ticker")) or _target_ticker(target)
        entity_ids = tuple(_item_entity_ids(data, target))
        fetched_at = (
            parse_datetime(data.get("fetched_at"))
            or parse_datetime(_value(package, "completed_at"))
            or timestamp_for_create(envelope)
        )
        title = _clean_key_value(data.get("title"))
        content = _clean_key_value(data.get("content"))
        content_preview = _clean_key_value(data.get("content_preview") or data.get("snippet"))
        url = _clean_key_value(data.get("url"))
        metadata = _to_mapping(data.get("metadata") or {})
        quality_notes = tuple(
            _clean_sequence(data.get("quality_notes"))
            + [
                note
                for note in _clean_sequence(metadata.get("quality_notes"))
                if note not in _clean_sequence(data.get("quality_notes"))
            ]
        )

        raw = RawItemDraft(
            source=source,
            source_type=source_type,
            ticker=ticker,
            entity_ids=entity_ids,
            title=title,
            content=content,
            content_preview=content_preview,
            url=url,
            publish_time=publish_time,
            fetched_at=fetched_at,
            author=_clean_key_value(data.get("author")),
            language=_clean_key_value(data.get("language")),
            raw_payload=dict(data.get("raw_payload") or {}),
        )
        evidence = EvidenceItemDraft(
            ticker=ticker,
            entity_ids=entity_ids,
            source=source,
            source_type=source_type,
            evidence_type=_evidence_type(data, package, source_type),
            title=title,
            content=content or content_preview or title,
            url=url,
            publish_time=publish_time,
            fetched_at=fetched_at,
            source_quality=_as_float(
                data.get("source_quality")
                if data.get("source_quality") is not None
                else data.get("source_quality_hint")
            ),
            relevance=_as_float(data.get("relevance")),
            freshness=_as_float(data.get("freshness"))
            if data.get("freshness") is not None
            else freshness(publish_time, envelope.analysis_time),
            quality_notes=quality_notes,
        )
        return NormalizedEvidenceDraft(
            raw=raw,
            evidence=evidence,
            external_id=external_id,
            dedupe_keys=tuple(_dedupe_keys(data, package, primary_key)),
        )


def _iter_package_items(package: Any) -> list[Any]:
    if package is None:
        return []
    if isinstance(package, Mapping):
        for key in ("items", "results", "search_results"):
            value = package.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return list(value)
        return [package]
    if isinstance(package, Sequence) and not isinstance(package, (str, bytes, bytearray)):
        return list(package)
    for attr in ("items", "results", "search_results"):
        value = getattr(package, attr, None)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return list(value)
    return [package]


def _item_dedupe_key(data: Mapping[str, Any], package: Any) -> str | None:
    source = _item_source(data, package)
    url = _clean_key_value(data.get("url"))
    if url is not None:
        return f"source:{source}:url:{url}"
    external_id = _clean_key_value(data.get("external_id"))
    if external_id is not None:
        return f"source:{source}:external_id:{external_id}"
    return None


def _dedupe_keys(data: Mapping[str, Any], package: Any, primary_item_key: str) -> list[str]:
    keys = [primary_item_key]
    source = _item_source(data, package)
    external_id = _clean_key_value(data.get("external_id"))
    if external_id is not None:
        external_key = f"source:{source}:external_id:{external_id}"
        if external_key not in keys:
            keys.append(external_key)
    content_key = _content_dedupe_key(data, package)
    if content_key is not None and content_key not in keys:
        keys.append(content_key)
    return keys


def _content_dedupe_key(data: Mapping[str, Any], package: Any) -> str | None:
    content = _clean_key_value(data.get("content"))
    if content is None:
        return None
    target = _value(package, "target")
    ticker = _clean_key_value(data.get("ticker")) or _target_ticker(target) or "unknown"
    entities = ",".join(_item_entity_ids(data, target))
    publish_time = _clean_key_value(data.get("publish_time") or data.get("published_at")) or "unknown"
    digest = sha256(content.encode("utf-8")).hexdigest()
    return f"content:{ticker}:{entities}:{publish_time}:{digest}"


def _item_source(data: Mapping[str, Any], package: Any) -> str:
    return (
        _clean_key_value(data.get("source"))
        or _clean_key_value(_value(package, "source"))
        or "unknown"
    )


def _evidence_type(
    data: Mapping[str, Any],
    package: Any,
    source_type: str | None,
) -> str:
    metadata = _to_mapping(data.get("metadata") or {})
    package_metadata = _to_mapping(_value(package, "metadata", {}) or {})
    return (
        _clean_key_value(data.get("evidence_type"))
        or _clean_key_value(metadata.get("evidence_type"))
        or _clean_key_value(package_metadata.get("evidence_type"))
        or _clean_key_value(source_type)
        or "unknown"
    )


def _item_entity_ids(data: Mapping[str, Any], target: Any) -> list[str]:
    values = _clean_sequence(data.get("entity_ids"))
    target_entity = _clean_key_value(_value(target, "entity_id"))
    if target_entity is not None and target_entity not in values:
        values.append(target_entity)
    return values


def _target_ticker(target: Any) -> str | None:
    ticker = _clean_key_value(_value(target, "ticker"))
    if ticker is not None:
        return ticker
    stock_code = _clean_key_value(_value(target, "stock_code"))
    if stock_code is None:
        return None
    return stock_code.split(".", 1)[0]


def _rejected(external_id: str | None, reason: str, message: str) -> IngestRejectedItem:
    from consensusinvest.evidence_store.models import IngestRejectedItem

    return IngestRejectedItem(
        external_id=external_id,
        reason=reason,
        message=message,
        code=reason,
    )


def ingest_context(envelope: InternalCallEnvelope, *, task_id: str | None) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "workflow_run_id": envelope.workflow_run_id,
        "requested_by": envelope.requested_by,
        "correlation_id": envelope.correlation_id,
    }


def _normalization_status(
    raw_items: list[RawItem],
    rejected_items: list[IngestRejectedItem],
) -> str:
    if raw_items and rejected_items:
        return "partial_accepted"
    if raw_items:
        return "accepted"
    return "rejected"


def coerce_dataclass(cls: type[_T], value: Any) -> _T:
    if isinstance(value, cls):
        return value
    data = _to_mapping(value)
    allowed = {field.name for field in fields(cls)}
    return cls(**{key: data[key] for key in allowed if key in data})


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    result: dict[str, Any] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        if callable(attr):
            continue
        result[name] = attr
    return result


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def find_forbidden_fact_key(
    value: Any,
    *,
    skip_keys: set[str] | None = None,
    path: str = "",
) -> str | None:
    skip = skip_keys or set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_norm = key_text.strip().lower()
            child_path = f"{path}.{key_text}" if path else key_text
            if key_norm in skip:
                continue
            if key_norm in FORBIDDEN_FACT_FIELDS:
                return child_path
            found = find_forbidden_fact_key(child, skip_keys=skip, path=child_path)
            if found is not None:
                return found
    elif is_dataclass(value) and not isinstance(value, type):
        return find_forbidden_fact_key(asdict(value), skip_keys=skip, path=path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            found = find_forbidden_fact_key(child, skip_keys=skip, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _clean_key_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _clean_key_value(value)
        return [cleaned] if cleaned is not None else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            cleaned = _clean_key_value(item)
            if cleaned is not None and cleaned not in result:
                result.append(cleaned)
        return result
    cleaned = _clean_key_value(value)
    return [cleaned] if cleaned is not None else []


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def timestamp_for_create(envelope: InternalCallEnvelope) -> datetime:
    return envelope.analysis_time or datetime.now(UTC)


def datetime_after(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return comparable_datetime(left) > comparable_datetime(right)


def comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def freshness(publish_time: datetime | None, analysis_time: datetime | None) -> float | None:
    if publish_time is None or analysis_time is None:
        return None
    delta_days = (
        comparable_datetime(analysis_time) - comparable_datetime(publish_time)
    ).total_seconds() / 86400
    if delta_days < 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - delta_days / 365.0))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "EvidenceNormalizer",
    "FORBIDDEN_FACT_FIELDS",
    "coerce_dataclass",
    "comparable_datetime",
    "datetime_after",
    "find_forbidden_fact_key",
    "freshness",
    "ingest_context",
    "parse_datetime",
    "timestamp_for_create",
]
