"""Runtime reader adapter for Report Module view assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from consensusinvest.agent_swarm.models import JudgmentRecord
from consensusinvest.agent_swarm.repository import InMemoryAgentSwarmRepository
from consensusinvest.entities.repository import EntityRecord, InMemoryEntityRepository
from consensusinvest.evidence_store.client import EvidenceStoreClient
from consensusinvest.evidence_store.models import EvidenceDetail, EvidenceQuery, MarketSnapshot, MarketSnapshotQuery
from consensusinvest.runtime.wiring import AppRuntime

from ._utils import _query_envelope
from .evidence_projection import _detail_or_item, _entity_by_id
from .projections import _stock_code, _ticker

@dataclass(slots=True)
class ReportRuntimeReader:
    evidence_store: EvidenceStoreClient
    entity_repository: InMemoryEntityRepository
    agent_repository: InMemoryAgentSwarmRepository
    workflow_repository: Any | None = None
    search_pool: Any | None = None
    report_repository: Any | None = None

    @classmethod
    def from_runtime(cls, runtime: AppRuntime, report_repository: Any | None = None) -> ReportRuntimeReader:
        return cls(
            evidence_store=runtime.evidence_store,
            entity_repository=runtime.entity_repository,
            agent_repository=runtime.agent_repository,
            workflow_repository=runtime.workflow_repository,
            search_pool=runtime.search_pool,
            report_repository=report_repository or getattr(runtime, "report_repository", None),
        )

    def search_entities(self, keyword: str, limit: int) -> list[EntityRecord]:
        rows, _ = self.entity_repository.list_entities(query=keyword, limit=limit, offset=0)
        return [row for row in rows if _stock_code(row) is not None]

    def find_entity_by_stock_code(self, stock_code: str) -> EntityRecord | None:
        needle = stock_code.strip().lower()
        rows, _ = self.entity_repository.list_entities(limit=1000, offset=0)
        for row in rows:
            values = {_stock_code(row), _ticker(row), *row.aliases}
            if any(value and value.lower() == needle for value in values):
                return row
        return None

    def evidence_for_entity(self, entity_id: str, *, limit: int = 20) -> list[EvidenceDetail]:
        page = self.evidence_store.query_evidence(
            _query_envelope(),
            EvidenceQuery(entity_ids=(entity_id,), limit=limit, offset=0),
        )
        return [_detail_or_item(self.evidence_store, item) for item in page.items]

    def evidence_for_keyword(self, keyword: str, *, limit: int) -> list[EvidenceDetail]:
        needle = keyword.strip().lower()
        if not needle:
            return []
        page = self.evidence_store.query_evidence(
            _query_envelope(),
            EvidenceQuery(limit=500, offset=0),
        )
        hits: list[EvidenceDetail] = []
        for item in page.items:
            haystacks = [item.title or "", item.content or "", item.evidence_type or ""]
            detail = _detail_or_item(self.evidence_store, item)
            if detail.structure is not None:
                haystacks.append(detail.structure.objective_summary)
            if any(needle in value.lower() for value in haystacks):
                hits.append(detail)
            if len(hits) >= limit:
                break
        return hits

    def judgment_by_workflow(self, workflow_run_id: str) -> JudgmentRecord | None:
        return self.agent_repository.get_judgment_by_workflow(workflow_run_id)

    def latest_judgment_for_entity(self, entity_id: str) -> JudgmentRecord | None:
        if self.workflow_repository is None:
            return None
        entity = _entity_by_id(self.entity_repository, entity_id)
        if entity is None:
            return None
        ticker = _ticker(entity)
        stock_code = _stock_code(entity)
        if ticker is None:
            return None

        offset = 0
        limit = 100
        while True:
            rows, total = self.workflow_repository.list_runs(ticker=ticker, limit=limit, offset=offset)
            for run in rows:
                if run.entity_id is not None and run.entity_id != entity_id:
                    continue
                if stock_code is not None and run.stock_code not in {None, stock_code}:
                    continue
                judgment = self.agent_repository.get_judgment_by_workflow(run.workflow_run_id)
                if judgment is not None:
                    return judgment
            offset += len(rows)
            if not rows or offset >= total:
                break
        return None

    def market_snapshots(self, snapshot_types: tuple[str, ...], *, limit: int = 50) -> list[MarketSnapshot]:
        page = self.evidence_store.query_market_snapshots(
            _query_envelope(),
            MarketSnapshotQuery(snapshot_types=snapshot_types, limit=limit, offset=0),
        )
        return page.items

    def market_snapshots_for_ticker(
        self,
        ticker: str,
        snapshot_types: tuple[str, ...],
        *,
        limit: int = 50,
    ) -> list[MarketSnapshot]:
        page = self.evidence_store.query_market_snapshots(
            _query_envelope(),
            MarketSnapshotQuery(ticker=ticker, snapshot_types=snapshot_types, limit=limit, offset=0),
        )
        return page.items
