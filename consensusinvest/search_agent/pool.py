from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
import inspect
from typing import Any

from .models import SearchResultPackage, SearchTask, SearchTaskStatus, SourceStatus
from .providers import ProviderSearchResponse, SearchExpansionCandidate, SearchProvider
from .repository import SQLiteSearchTaskRepository


@dataclass(init=False, slots=True)
class SearchAgentPool:
    repository: SQLiteSearchTaskRepository = field(default_factory=SQLiteSearchTaskRepository)
    provider: SearchProvider | None = None
    providers: dict[str, Any] = field(default_factory=dict)
    evidence_client: Any = None
    _envelopes: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        provider_registry: dict[str, Any] | None = None,
        evidence_store_client: Any | None = None,
        *,
        repository: SQLiteSearchTaskRepository | None = None,
        provider: SearchProvider | None = None,
        providers: dict[str, Any] | None = None,
        evidence_store: Any | None = None,
        evidence_client: Any | None = None,
    ) -> None:
        self.repository = repository or SQLiteSearchTaskRepository()
        self.provider = provider
        self.providers = providers or provider_registry or {}
        self.evidence_client = evidence_client or evidence_store_client or evidence_store
        self._envelopes = {}

    def submit(self, envelope: Any, task: SearchTask) -> Any:
        if not isinstance(task, SearchTask):
            task = SearchTask(**task)
        validate_for_create = getattr(envelope, "validate_for_create", None)
        if callable(validate_for_create):
            validate_for_create()
        ingest_target = _value(task.callback, "ingest_target")
        if ingest_target != "evidence_store":
            raise ValueError("SearchTask.callback.ingest_target must be evidence_store")
        envelope_key = _value(envelope, "idempotency_key")
        if task.idempotency_key is None and envelope_key is not None:
            task = SearchTask(
                target=task.target,
                scope=task.scope,
                constraints=task.constraints,
                idempotency_key=envelope_key,
                task_type=task.task_type,
                callback=task.callback,
                metadata=task.metadata,
            )
        if task.idempotency_key is None:
            raise ValueError("idempotency_key is required for SearchTask submission")
        task_id, status = self.repository.create_task(task)
        self._envelopes[task_id] = envelope
        idempotency_key = task.idempotency_key or envelope_key
        receipt_type = _runtime_symbol("AsyncTaskReceipt")
        if receipt_type is None:
            return {
                "task_id": task_id,
                "status": status,
                "accepted_at": datetime.now(UTC),
                "idempotency_key": idempotency_key,
                "poll_after_ms": 1000,
            }
        return _build_runtime_object(
            receipt_type,
            task_id=task_id,
            status=status,
            accepted_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
            poll_after_ms=1000,
        )

    def get_status(self, envelope: Any, task_id: str) -> Any:
        status = self.repository.get_task_status(task_id)
        if status is None:
            error_type = _runtime_symbol("InternalError")
            if error_type is None:
                return {"error": "search_task_not_found", "task_id": task_id}
            return _build_runtime_object(
                error_type,
                code="search_task_not_found",
                message=f"Search task not found: {task_id}",
            )
        return status

    def run_pending_once(self) -> list[str]:
        task_ids = self.repository.list_task_ids_by_statuses(
            (SearchTaskStatus.QUEUED, SearchTaskStatus.RUNNING)
        )
        for task_id in task_ids:
            task = self.repository.get_task(task_id)
            if task is None:
                continue
            self._run_task(task_id, task, self._envelopes.get(task_id))
        return task_ids

    def run_task_once(self, task_id: str) -> bool:
        status = self.repository.get_task_status(task_id)
        status_value = _value(status, "status", status)
        if status_value not in (
            SearchTaskStatus.QUEUED,
            SearchTaskStatus.RUNNING,
            SearchTaskStatus.FAILED,
            SearchTaskStatus.QUEUED.value,
            SearchTaskStatus.RUNNING.value,
            SearchTaskStatus.FAILED.value,
        ):
            return False
        task = self.repository.get_task(task_id)
        if task is None:
            return False
        self._run_task(task_id, task, self._envelopes.get(task_id))
        return True

    def _run_task(self, task_id: str, task: SearchTask, envelope: Any) -> None:
        self.repository.update_task_status(task_id, SearchTaskStatus.RUNNING)

        provider_calls_left = task.constraints.budget.max_provider_calls
        results_left = task.scope.max_results
        success_count = 0
        failure_count = 0
        skipped_count = 0
        found_count = 0

        sources = tuple(task.scope.sources)
        for index, source in enumerate(sources):
            if results_left is not None and results_left <= 0:
                self.repository.upsert_source_status(
                    task_id,
                    source,
                    SourceStatus.SKIPPED,
                    error="max_results_exhausted",
                )
                self.repository.append_event(
                    task_id,
                    "search.source_skipped",
                    {
                        "task_id": task_id,
                        "source": source,
                        "reason": "max_results_exhausted",
                    },
                )
                skipped_count += 1
                continue

            source_results_left = _source_result_limit(
                results_left,
                remaining_sources=len(sources) - index,
            )
            if provider_calls_left <= 0:
                self.repository.upsert_source_status(
                    task_id,
                    source,
                    SourceStatus.SKIPPED,
                    error="provider_call_budget_exhausted",
                )
                self.repository.append_event(
                    task_id,
                    "search.source_skipped",
                    {
                        "task_id": task_id,
                        "source": source,
                        "reason": "provider_call_budget_exhausted",
                    },
                )
                skipped_count += 1
                continue

            try:
                provider = self._provider_for(source)
                provider_calls_left -= 1
                provider_task = _task_with_max_results(task, source_results_left)
                worker_id = _worker_id(task_id, source)
                self.repository.upsert_source_status(task_id, source, SourceStatus.RUNNING)
                self.repository.append_event(
                    task_id,
                    "search.source_started",
                    {
                        "task_id": task_id,
                        "source": source,
                        "worker_id": worker_id,
                    },
                )
                response = _normalize_provider_response(
                    _call_search(provider, envelope, source, provider_task),
                    source,
                    task_id,
                )
                response, expansion_calls_used = self._apply_expansions(
                    task_id,
                    provider_task,
                    envelope,
                    source,
                    response,
                    provider_calls_left,
                    source_results_left,
                )
                provider_calls_left -= expansion_calls_used
                response = _limit_response(response, source_results_left)
                self._append_item_found_events(task_id, source, response)
                ingested_count = self._ingest(envelope, task_id, provider_task, source, response)
                found_count += len(response.items)
                if results_left is not None:
                    results_left -= len(response.items)
                self.repository.upsert_source_status(
                    task_id,
                    source,
                    SourceStatus.COMPLETED,
                    items_count=len(response.items),
                    ingested_count=ingested_count,
                )
                success_count += 1
            except Exception as exc:
                self.repository.upsert_source_status(
                    task_id,
                    source,
                    SourceStatus.FAILED,
                    error=str(exc),
                )
                self.repository.append_event(
                    task_id,
                    "search.source_failed",
                    {
                        "task_id": task_id,
                        "source": source,
                        "error": {
                            "code": "provider_error",
                            "message": str(exc),
                        },
                    },
                )
                failure_count += 1

        final_status = _final_status(success_count, failure_count + skipped_count)
        self.repository.update_task_status(task_id, final_status)
        self.repository.append_event(
            task_id,
            "search.task_completed",
            {
                "task_id": task_id,
                "status": final_status.value,
                "found_count": found_count,
                "successful_sources": success_count,
                "failed_sources": failure_count,
                "skipped_sources": skipped_count,
            },
        )

    def _apply_expansions(
        self,
        task_id: str,
        task: SearchTask,
        envelope: Any,
        source: str,
        response: ProviderSearchResponse,
        provider_calls_left: int,
        max_items: int | None,
    ) -> tuple[ProviderSearchResponse, int]:
        policy = task.constraints.expansion_policy
        items = list(response.items)
        expansion_calls_used = 0

        for candidate in response.expansion_candidates:
            if max_items is not None and len(items) >= max_items:
                self.repository.append_event(
                    task_id,
                    "search.expansion_skipped_max_results_exhausted",
                    {"source": source, "action": candidate.action},
                )
                continue
            if not policy.allowed:
                self.repository.append_event(
                    task_id,
                    "search.expansion_skipped_not_allowed",
                    {"source": source, "action": candidate.action},
                )
                continue
            if candidate.action not in policy.allowed_actions:
                self.repository.append_event(
                    task_id,
                    "search.expansion_skipped_action_not_allowed",
                    {"source": source, "action": candidate.action},
                )
                continue
            if expansion_calls_used >= max(policy.max_depth, 0):
                self.repository.append_event(
                    task_id,
                    "search.expansion_skipped_depth_exhausted",
                    {"source": source, "action": candidate.action},
                )
                continue
            if provider_calls_left <= 0:
                self.repository.append_event(
                    task_id,
                    "search.expansion_skipped_budget_exhausted",
                    {"source": source, "action": candidate.action},
                )
                continue

            provider_calls_left -= 1
            expansion_calls_used += 1
            expanded = _normalize_provider_response(
                _call_expand(self._provider_for(source), envelope, source, task, candidate),
                source,
                task_id,
            )
            items.extend(expanded.items)
            self.repository.append_event(
                task_id,
                "search.expansion_completed",
                {
                    "source": source,
                    "action": candidate.action,
                    "items_count": len(expanded.items),
                },
            )

        self.repository.append_event(
            task_id,
            "search.expansion_budget_used",
            {"source": source, "provider_calls": expansion_calls_used},
        )
        return ProviderSearchResponse(
            items=tuple(items),
            expansion_candidates=response.expansion_candidates,
            worker_id=response.worker_id,
            source_type=response.source_type,
            completed_at=response.completed_at,
        ), expansion_calls_used

    def _ingest(
        self,
        envelope: Any,
        task_id: str,
        task: SearchTask,
        source: str,
        response: ProviderSearchResponse,
    ) -> int:
        package = SearchResultPackage(
            task_id=task_id,
            worker_id=response.worker_id or _worker_id(task_id, source),
            source=source,
            source_type=response.source_type,
            target=task.target,
            items=response.items,
            completed_at=response.completed_at or datetime.now(UTC).isoformat(),
        )
        if task.task_type == "market_snapshot":
            saved_count = self._ingest_market_snapshots(
                envelope,
                task_id,
                task,
                source,
                response,
            )
            self.repository.append_event(
                task_id,
                "search.item_ingested",
                {
                    "task_id": task_id,
                    "source": source,
                    "ingested_count": saved_count,
                },
            )
            return saved_count

        result = _call_ingest(self.evidence_client, envelope, package)
        self.repository.append_event(
            task_id,
            "search.item_ingested",
            {
                "task_id": task_id,
                "source": source,
                "ingested_count": _ingested_count(result),
            },
        )
        return _ingested_count(result)

    def _ingest_market_snapshots(
        self,
        envelope: Any,
        task_id: str,
        task: SearchTask,
        source: str,
        response: ProviderSearchResponse,
    ) -> int:
        save_market_snapshot = getattr(self.evidence_client, "save_market_snapshot", None)
        if not callable(save_market_snapshot):
            raise RuntimeError("EvidenceStore.save_market_snapshot is required for market_snapshot SearchTask")

        saved_count = 0
        for item in response.items:
            snapshot, rejection = _market_snapshot_from_item(item, task, source)
            if rejection is not None:
                self._append_item_rejected_event(task_id, source, item, rejection)
                continue

            try:
                save_market_snapshot(envelope, snapshot)
            except Exception as exc:
                self._append_item_rejected_event(
                    task_id,
                    source,
                    item,
                    {
                        "reason": _snapshot_save_rejection_reason(exc),
                        "message": str(exc),
                    },
                )
                continue
            saved_count += 1
        return saved_count

    def _append_item_found_events(
        self,
        task_id: str,
        source: str,
        response: ProviderSearchResponse,
    ) -> None:
        for item in response.items:
            self.repository.append_event(
                task_id,
                "search.item_found",
                {
                    "task_id": task_id,
                    "source": source,
                    "external_id": _value(item, "external_id"),
                    "url": _value(item, "url"),
                    "title": _value(item, "title"),
                },
            )

    def _append_item_rejected_event(
        self,
        task_id: str,
        source: str,
        item: Any,
        rejection: dict[str, Any],
    ) -> None:
        self.repository.append_event(
            task_id,
            "search.item_rejected",
            {
                "task_id": task_id,
                "source": source,
                "external_id": _value(item, "external_id"),
                **rejection,
            },
        )

    def _provider_for(self, source: str) -> Any:
        if source in self.providers:
            return self.providers[source]
        if self.provider is not None:
            return self.provider
        raise RuntimeError(f"missing search provider for source: {source}")

    def unavailable_sources(self, sources: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        if self.provider is not None:
            return ()
        return tuple(source for source in sources if source not in self.providers)


def _final_status(success_count: int, failure_count: int) -> SearchTaskStatus:
    if success_count > 0 and failure_count > 0:
        return SearchTaskStatus.PARTIAL_COMPLETED
    if success_count > 0:
        return SearchTaskStatus.COMPLETED
    return SearchTaskStatus.FAILED


def _ingested_count(result: Any) -> int:
    for name in ("ingested_count", "evidence_count", "count", "accepted_count"):
        value = getattr(result, name, None)
        if isinstance(value, int):
            return value
    count = 0
    for name in ("created_evidence_ids", "updated_evidence_ids"):
        value = getattr(result, name, None)
        if isinstance(value, list):
            count += len(value)
    if count:
        return count
    raw_refs = getattr(result, "accepted_raw_refs", None)
    if isinstance(raw_refs, list):
        return len(raw_refs)
    if isinstance(result, dict):
        count = 0
        for name in ("created_evidence_ids", "updated_evidence_ids"):
            value = result.get(name)
            if isinstance(value, list):
                count += len(value)
        if count:
            return count
        raw_refs = result.get("accepted_raw_refs")
        if isinstance(raw_refs, list):
            return len(raw_refs)
        for name in ("ingested_count", "evidence_count", "count", "accepted_count"):
            value = result.get(name)
            if isinstance(value, int):
                return value
    return 0


def _runtime_symbol(name: str) -> Any:
    try:
        import consensusinvest.runtime.models as runtime_models
    except ModuleNotFoundError:
        return None
    return getattr(runtime_models, name, None)


def _build_runtime_object(factory: Any, **values: Any) -> Any:
    try:
        return factory(**values)
    except TypeError:
        try:
            return factory(values["task_id"], values["status"])
        except (KeyError, TypeError):
            return values


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _call_search(provider: Any, envelope: Any, source: str, task: SearchTask) -> Any:
    params = list(inspect.signature(provider.search).parameters)
    if params and params[0] in {"envelope", "call_envelope"}:
        return provider.search(envelope, task)
    return provider.search(source, task)


def _call_expand(
    provider: Any,
    envelope: Any,
    source: str,
    task: SearchTask,
    candidate: SearchExpansionCandidate,
) -> Any:
    params = list(inspect.signature(provider.expand).parameters)
    if params and params[0] in {"envelope", "call_envelope"}:
        return provider.expand(envelope, task, candidate.action, seed_item=candidate.item)
    return provider.expand(source, task, candidate)


def _call_ingest(evidence_client: Any, envelope: Any, package: SearchResultPackage) -> Any:
    return evidence_client.ingest_search_result(envelope, package)


def _market_snapshot_from_item(
    item: Any,
    task: SearchTask,
    source: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    violation_path = _find_directional_field(item)
    if violation_path is not None:
        return None, {
            "reason": "write_boundary_violation",
            "message": f"directional field is not allowed in MarketSnapshot: {violation_path}",
        }

    required = ("snapshot_type", "metrics", "snapshot_time")
    missing = [name for name in required if _explicit_item_value(item, name, _MISSING) is _MISSING]
    if missing:
        return None, {
            "reason": "missing_market_snapshot_field",
            "message": "market_snapshot item must explicitly include snapshot_type, metrics, and snapshot_time",
            "missing_fields": missing,
        }

    snapshot_type = _explicit_item_value(item, "snapshot_type")
    metrics = _explicit_item_value(item, "metrics")
    snapshot_time = _explicit_item_value(item, "snapshot_time")
    if snapshot_type is None or metrics is None or snapshot_time is None:
        return None, {
            "reason": "invalid_market_snapshot_field",
            "message": "market_snapshot required fields cannot be null",
        }
    if not isinstance(metrics, Mapping):
        return None, {
            "reason": "invalid_market_snapshot_field",
            "message": "market_snapshot metrics must be an object",
        }

    item_mapping = _item_mapping(item)
    ticker = _optional_item_value(item, "ticker", _value(task.target, "ticker"))
    entity_ids = _snapshot_entity_ids(item, task)
    fetched_at = _explicit_item_value(item, "fetched_at", None)
    item_source = _optional_item_value(item, "source", source)

    snapshot = {
        "snapshot_type": snapshot_type,
        "ticker": ticker,
        "entity_ids": entity_ids,
        "source": item_source,
        "snapshot_time": snapshot_time,
        "metrics": dict(metrics),
    }
    if fetched_at is not None:
        snapshot["fetched_at"] = fetched_at
    return snapshot, None


def _snapshot_entity_ids(item: Any, task: SearchTask) -> tuple[str, ...]:
    explicit_entity_ids = _explicit_item_value(item, "entity_ids", _MISSING)
    if explicit_entity_ids is not _MISSING and explicit_entity_ids is not None:
        if isinstance(explicit_entity_ids, str):
            return (explicit_entity_ids,)
        return tuple(explicit_entity_ids)

    explicit_entity_id = _explicit_item_value(item, "entity_id", _MISSING)
    if explicit_entity_id is not _MISSING and explicit_entity_id is not None:
        return (str(explicit_entity_id),)

    target_entity_id = _value(task.target, "entity_id")
    if target_entity_id is None:
        return ()
    return (str(target_entity_id),)


def _explicit_item_value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping) and name in item:
        return item[name]
    if hasattr(item, name):
        return getattr(item, name)
    metadata = _value(item, "metadata")
    if isinstance(metadata, Mapping) and name in metadata:
        return metadata[name]
    return default


def _optional_item_value(item: Any, name: str, default: Any = None) -> Any:
    value = _explicit_item_value(item, name, _MISSING)
    if value is _MISSING or value is None:
        return default
    return value


def _item_mapping(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    fields = getattr(item, "__dataclass_fields__", None)
    if fields is not None:
        return {name: getattr(item, name) for name in fields}
    result: dict[str, Any] = {}
    for name in dir(item):
        if name.startswith("_"):
            continue
        try:
            value = getattr(item, name)
        except Exception:
            continue
        if not callable(value):
            result[name] = value
    return result


def _find_directional_field(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text.strip().lower() in _DIRECTIONAL_MARKET_FIELDS:
                return child_path
            found = _find_directional_field(child, child_path)
            if found is not None:
                return found
    elif isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            found = _find_directional_field(child, f"{path}[{index}]")
            if found is not None:
                return found
    else:
        fields = getattr(value, "__dataclass_fields__", None)
        if fields is not None:
            return _find_directional_field(_item_mapping(value), path)
    return None


def _snapshot_save_rejection_reason(exc: Exception) -> str:
    message = str(exc)
    if "write_boundary_violation" in message:
        return "write_boundary_violation"
    if "snapshot_time" in message and "analysis_time" in message:
        return "snapshot_time_after_analysis_time"
    if "snapshot_time is required" in message:
        return "missing_market_snapshot_field"
    if "invalid_snapshot_type" in message:
        return "invalid_snapshot_type"
    return "market_snapshot_save_failed"


def _normalize_provider_response(raw: Any, source: str, task_id: str) -> ProviderSearchResponse:
    if isinstance(raw, ProviderSearchResponse):
        return raw
    if isinstance(raw, dict):
        items = tuple(raw.get("items", ()))
        candidates = tuple(
            SearchExpansionCandidate(
                action=item["action"],
                item=item.get("item") or item.get("seed_item") or {},
            )
            for item in raw.get("expansion_requests", ())
            if "action" in item
        )
        return ProviderSearchResponse(
            items=items,
            expansion_candidates=candidates,
            worker_id=raw.get("worker_id"),
            source_type=raw.get("source_type"),
            completed_at=raw.get("completed_at"),
        )
    items = tuple(_value(raw, "items", ()))
    candidates = tuple(_value(raw, "expansion_candidates", ()))
    if candidates:
        return ProviderSearchResponse(
            items=items,
            expansion_candidates=candidates,
            worker_id=_value(raw, "worker_id"),
            source_type=_value(raw, "source_type"),
            completed_at=_value(raw, "completed_at"),
        )
    requests = tuple(_value(raw, "expansion_requests", ()))
    return ProviderSearchResponse(
        items=items,
        expansion_candidates=tuple(
            SearchExpansionCandidate(
                action=_value(item, "action"),
                item=_value(item, "item", _value(item, "seed_item", {})),
            )
            for item in requests
            if _value(item, "action")
        ),
        worker_id=_value(raw, "worker_id"),
        source_type=_value(raw, "source_type"),
        completed_at=_value(raw, "completed_at"),
    )


def _limit_response(
    response: ProviderSearchResponse,
    max_items: int | None,
) -> ProviderSearchResponse:
    if max_items is None:
        return response
    return ProviderSearchResponse(
        items=tuple(response.items[: max(max_items, 0)]),
        expansion_candidates=response.expansion_candidates,
        worker_id=response.worker_id,
        source_type=response.source_type,
        completed_at=response.completed_at,
    )


def _source_result_limit(results_left: int | None, *, remaining_sources: int) -> int | None:
    if results_left is None:
        return None
    return max(1, results_left // max(remaining_sources, 1))


def _task_with_max_results(task: SearchTask, max_results: int | None) -> SearchTask:
    if max_results == task.scope.max_results:
        return task
    return replace(task, scope=replace(task.scope, max_results=max_results))


def _worker_id(task_id: str, source: str) -> str:
    return f"search_worker_{task_id}_{source}"


_MISSING = object()

_DIRECTIONAL_MARKET_FIELDS = {
    "action",
    "bearish",
    "bullish",
    "buy",
    "hold",
    "investment_action",
    "net_impact",
    "recommendation",
    "sell",
    "signal",
    "suggested_action",
    "trade_signal",
    "trading_signal",
}
