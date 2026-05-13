from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import SearchResultItem, SearchTask


@dataclass(frozen=True, slots=True)
class SearchExpansionCandidate:
    action: str
    item: SearchResultItem | dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderSearchResponse:
    items: tuple[SearchResultItem | dict[str, Any], ...] = ()
    expansion_candidates: tuple[SearchExpansionCandidate, ...] = ()
    worker_id: str | None = None
    source_type: str | None = None
    completed_at: str | None = None


class SearchProvider(Protocol):
    def search(self, source: str, task: SearchTask) -> ProviderSearchResponse:
        ...

    def expand(
        self,
        source: str,
        task: SearchTask,
        candidate: SearchExpansionCandidate,
    ) -> ProviderSearchResponse:
        ...


@dataclass(slots=True)
class MockSearchProvider:
    items_by_source: dict[str, tuple[SearchResultItem, ...]] = field(default_factory=dict)
    errors_by_source: dict[str, Exception | str] = field(default_factory=dict)
    expansion_candidates_by_source: dict[str, tuple[SearchExpansionCandidate, ...]] = field(
        default_factory=dict
    )
    expansion_items_by_action: dict[str, tuple[SearchResultItem, ...]] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search(self, source: str, task: SearchTask) -> ProviderSearchResponse:
        self.calls.append(("search", source))
        self._raise_if_configured(source)
        return ProviderSearchResponse(
            items=self.items_by_source.get(source, ()),
            expansion_candidates=self.expansion_candidates_by_source.get(source, ()),
        )

    def expand(
        self,
        source: str,
        task: SearchTask,
        candidate: SearchExpansionCandidate,
    ) -> ProviderSearchResponse:
        self.calls.append((f"expand:{candidate.action}", source))
        self._raise_if_configured(source)
        return ProviderSearchResponse(items=self.expansion_items_by_action.get(candidate.action, ()))

    def _raise_if_configured(self, source: str) -> None:
        error = self.errors_by_source.get(source)
        if error is None:
            return
        if isinstance(error, Exception):
            raise error
        raise RuntimeError(error)
