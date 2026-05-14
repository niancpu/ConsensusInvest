from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SearchTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class SearchTarget:
    query: str | None = None
    ticker: str | None = None
    stock_code: str | None = None
    entity_id: str | None = None
    entity_type: str | None = None
    keywords: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "keywords", tuple(self.keywords))


@dataclass(frozen=True, slots=True)
class SearchScope:
    sources: tuple[str, ...]
    evidence_types: tuple[str, ...] = ()
    lookback_days: int | None = None
    max_results: int | None = None
    locale: str | None = None
    time_range: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))


@dataclass(frozen=True, slots=True)
class SearchExpansionPolicy:
    allowed: bool = False
    allowed_actions: tuple[str, ...] = ()
    max_depth: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_actions", tuple(self.allowed_actions))


@dataclass(frozen=True, slots=True)
class SearchBudget:
    max_provider_calls: int
    max_runtime_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SearchCallback:
    event_name: str | None = None
    ingest_target: str | None = None
    workflow_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchConstraints:
    allow_stale_cache: bool | None = None
    dedupe_hint: bool | None = None
    language: str | None = None
    expansion_policy: SearchExpansionPolicy = field(default_factory=SearchExpansionPolicy)
    budget: SearchBudget = field(default_factory=lambda: SearchBudget(max_provider_calls=1))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.expansion_policy, dict):
            object.__setattr__(
                self,
                "expansion_policy",
                SearchExpansionPolicy(**self.expansion_policy),
            )
        if isinstance(self.budget, dict):
            object.__setattr__(self, "budget", SearchBudget(**self.budget))


@dataclass(frozen=True, slots=True)
class SearchTask:
    target: SearchTarget | dict[str, Any]
    scope: SearchScope | dict[str, Any]
    constraints: SearchConstraints = field(default_factory=SearchConstraints)
    idempotency_key: str | None = None
    task_type: str | None = None
    callback: SearchCallback | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.target, dict):
            object.__setattr__(self, "target", SearchTarget(**self.target))
        if isinstance(self.scope, dict):
            object.__setattr__(self, "scope", SearchScope(**self.scope))
        if isinstance(self.constraints, dict):
            object.__setattr__(self, "constraints", SearchConstraints(**self.constraints))
        if isinstance(self.callback, dict):
            object.__setattr__(self, "callback", SearchCallback(**self.callback))


@dataclass(frozen=True, slots=True)
class SearchResultItem:
    external_id: str | None = None
    source: str | None = None
    source_type: str | None = None
    title: str | None = None
    url: str | None = None
    content: str | None = None
    content_preview: str | None = None
    snippet: str | None = None
    publish_time: str | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    author: str | None = None
    language: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    source_quality_hint: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchResultPackage:
    task_id: str
    worker_id: str | None
    source: str
    source_type: str | None
    target: SearchTarget
    items: tuple[SearchResultItem | dict[str, Any], ...]
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
