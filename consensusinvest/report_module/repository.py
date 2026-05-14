"""Stub repositories standing in for the main system data layer.

The Report Module is documented as a pure consumer of:

- Entity (companies, industries, concepts, events)
- Evidence Store (Raw / Evidence / Structure)
- MarketSnapshot
- Workflow Trace / Judgment from the main analysis runtime

The main runtime isn't implemented yet in this repo. These fixtures provide a
deterministic, in-process backing for the view APIs so the contracts can be
exercised end-to-end. Anything written here should be readable as
"what a real Evidence Store / Main Runtime Query would return", not as
Report-Module-owned facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    name: str
    aliases: list[str]
    stock_code: str | None
    ticker: str | None
    exchange: str | None
    market: str | None
    kind: str  # company / industry / concept / event


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    entity_id: str
    title: str
    objective_summary: str
    published_at: str
    source_quality: float
    relevance: float
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JudgmentRecord:
    judgment_id: str
    workflow_run_id: str
    entity_id: str
    action_label: str
    action_signal: str
    action_reason: str
    benefits: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    key_evidence_ids: list[str]
    market_snapshot_ids: list[str]
    summary: str
    updated_at: str


@dataclass(frozen=True)
class MarketSnapshotRecord:
    snapshot_id: str
    entity_id: str | None
    kind: str  # index / stock / sentiment / concept / warning
    payload: dict[str, Any]
    updated_at: str


@dataclass(frozen=True)
class IndustryRecord:
    entity_id: str
    name: str
    policy_support_level: str
    policy_support_desc: str
    supply_demand_status: str
    competition_landscape: str
    referenced_evidence_ids: list[str]
    market_snapshot_ids: list[str]
    updated_at: str


@dataclass(frozen=True)
class WarningRecord:
    warning_id: str
    time: str
    title: str
    content: str
    severity: str
    related_stock_codes: list[str]
    related_entity_ids: list[str]
    snapshot_ids: list[str]
    evidence_ids: list[str]


@dataclass(frozen=True)
class ConceptRecord:
    concept_name: str
    entity_id: str
    status: str
    heat_score: int
    trend: str
    snapshot_ids: list[str]
    evidence_ids: list[str]


@dataclass(frozen=True)
class EventImpactRecord:
    event_name: str
    impact_score: int
    impact_level: str
    direction: str | None
    evidence_ids: list[str]
    workflow_run_id: str | None
    judgment_id: str | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Seed data — single demo stock (BYD 002594.SZ) plus a couple of market rows.
# --------------------------------------------------------------------------

_ENTITIES: dict[str, EntityRecord] = {
    "ent_company_002594": EntityRecord(
        entity_id="ent_company_002594",
        name="比亚迪",
        aliases=["BYD", "比亚迪股份"],
        stock_code="002594.SZ",
        ticker="002594",
        exchange="SZ",
        market="A_SHARE",
        kind="company",
    ),
    "ent_company_600519": EntityRecord(
        entity_id="ent_company_600519",
        name="贵州茅台",
        aliases=["Moutai", "茅台"],
        stock_code="600519.SH",
        ticker="600519",
        exchange="SH",
        market="A_SHARE",
        kind="company",
    ),
    "ent_industry_new_energy_vehicle": EntityRecord(
        entity_id="ent_industry_new_energy_vehicle",
        name="新能源汽车",
        aliases=["NEV", "新能源车"],
        stock_code=None,
        ticker=None,
        exchange=None,
        market=None,
        kind="industry",
    ),
    "ent_concept_low_altitude_economy": EntityRecord(
        entity_id="ent_concept_low_altitude_economy",
        name="低空经济",
        aliases=["Low Altitude Economy"],
        stock_code=None,
        ticker=None,
        exchange=None,
        market=None,
        kind="concept",
    ),
}


_EVIDENCE: dict[str, EvidenceRecord] = {
    "ev_20260513_002594_report_001": EvidenceRecord(
        evidence_id="ev_20260513_002594_report_001",
        entity_id="ent_company_002594",
        title="比亚迪 2026Q1 财务数据",
        objective_summary="收入和利润保持增长。",
        published_at="2026-04-30T00:00:00+08:00",
        source_quality=0.9,
        relevance=0.88,
        tags=["financial_report"],
    ),
    "ev_20260513_002594_report_003": EvidenceRecord(
        evidence_id="ev_20260513_002594_report_003",
        entity_id="ent_company_002594",
        title="2026Q1 现金流披露",
        objective_summary="经营性现金流同比下降，公告中提示需关注质量。",
        published_at="2026-04-30T00:00:00+08:00",
        source_quality=0.85,
        relevance=0.72,
        tags=["financial_report", "risk_disclosure"],
    ),
    "ev_20260513_002594_order_001": EvidenceRecord(
        evidence_id="ev_20260513_002594_order_001",
        entity_id="ent_company_002594",
        title="2026 年订单能见度",
        objective_summary="公开披露的在手订单同比增长。",
        published_at="2026-05-08T00:00:00+08:00",
        source_quality=0.8,
        relevance=0.7,
        tags=["company_news"],
    ),
    "ev_20260513_002594_macro_001": EvidenceRecord(
        evidence_id="ev_20260513_002594_macro_001",
        entity_id="ent_company_002594",
        title="降息预期升温",
        objective_summary="宏观研究机构上调降息概率。",
        published_at="2026-05-10T00:00:00+08:00",
        source_quality=0.75,
        relevance=0.6,
        tags=["macro"],
    ),
    "ev_20260513_002594_policy_001": EvidenceRecord(
        evidence_id="ev_20260513_002594_policy_001",
        entity_id="ent_industry_new_energy_vehicle",
        title="2026 新能源汽车补贴接续政策",
        objective_summary="补贴接续政策延长至 2027 年。",
        published_at="2026-04-15T00:00:00+08:00",
        source_quality=0.92,
        relevance=0.81,
        tags=["policy"],
    ),
    "ev_20260513_002594_industry_002": EvidenceRecord(
        evidence_id="ev_20260513_002594_industry_002",
        entity_id="ent_industry_new_energy_vehicle",
        title="2026Q1 行业销量数据",
        objective_summary="头部厂商集中度继续提升。",
        published_at="2026-04-20T00:00:00+08:00",
        source_quality=0.88,
        relevance=0.77,
        tags=["industry"],
    ),
}


_JUDGMENTS: dict[str, JudgmentRecord] = {
    "jdg_20260513_002594_001": JudgmentRecord(
        judgment_id="jdg_20260513_002594_001",
        workflow_run_id="wr_20260513_002594_000001",
        entity_id="ent_company_002594",
        action_label="观望",
        action_signal="neutral",
        action_reason="等待价格确认基本面改善",
        benefits=[
            {
                "text": "订单能见度提升",
                "evidence_ids": ["ev_20260513_002594_order_001"],
                "source": "main_judgment_summary",
            }
        ],
        risks=[
            {
                "text": "现金流质量下降",
                "evidence_ids": ["ev_20260513_002594_report_003"],
                "source": "main_judgment_summary",
            }
        ],
        key_evidence_ids=["ev_20260513_002594_report_001", "ev_20260513_002594_report_003"],
        market_snapshot_ids=["mkt_snap_20260513_002594"],
        summary="基于指定主 workflow 的 Judgment 和 Evidence Structure 生成的报告摘要。",
        updated_at="2026-05-13T11:00:00+08:00",
    ),
}


_MARKET_SNAPSHOTS: dict[str, MarketSnapshotRecord] = {
    "mkt_snap_20260513_000001_sh": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_000001_sh",
        entity_id=None,
        kind="index",
        payload={
            "name": "上证指数",
            "code": "000001.SH",
            "value": 3120.55,
            "change_rate": 0.85,
            "is_up": True,
        },
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_399001_sz": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_399001_sz",
        entity_id=None,
        kind="index",
        payload={
            "name": "深证成指",
            "code": "399001.SZ",
            "value": 9870.21,
            "change_rate": 1.05,
            "is_up": True,
        },
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_index_sentiment": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_index_sentiment",
        entity_id=None,
        kind="sentiment",
        payload={"label": "中性偏多", "score": 62},
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_002594": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_002594",
        entity_id="ent_company_002594",
        kind="stock",
        payload={
            "price": 218.5,
            "change_rate": 2.15,
            "is_up": True,
            "view_score": 78,
            "view_label": "关注度较高",
        },
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_600519": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_600519",
        entity_id="ent_company_600519",
        kind="stock",
        payload={
            "price": 1720.0,
            "change_rate": -0.4,
            "is_up": False,
            "view_score": 65,
            "view_label": "关注度中等",
        },
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_concept_low_altitude": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_concept_low_altitude",
        entity_id="ent_concept_low_altitude_economy",
        kind="concept",
        payload={"heat_score": 86, "trend": "warming", "status": "升温"},
        updated_at="2026-05-13T11:05:00+08:00",
    ),
    "mkt_snap_20260513_warn_001": MarketSnapshotRecord(
        snapshot_id="mkt_snap_20260513_warn_001",
        entity_id=None,
        kind="warning",
        payload={
            "warning_id": "warn_20260513_094500_001",
            "time": "09:45",
            "title": "异动预警",
            "content": "某板块出现放量上攻",
            "severity": "notice",
            "related_stock_codes": ["002594.SZ"],
            "related_entity_ids": ["ent_concept_low_altitude_economy"],
        },
        updated_at="2026-05-13T09:45:00+08:00",
    ),
}


_INDUSTRY: dict[str, IndustryRecord] = {
    "ent_company_002594": IndustryRecord(
        entity_id="ent_industry_new_energy_vehicle",
        name="新能源汽车",
        policy_support_level="high",
        policy_support_desc="政策支持力度较强",
        supply_demand_status="供需紧平衡",
        competition_landscape="头部集中度提升",
        referenced_evidence_ids=[
            "ev_20260513_002594_policy_001",
            "ev_20260513_002594_industry_002",
        ],
        market_snapshot_ids=[],
        updated_at="2026-05-13T11:00:00+08:00",
    ),
}


_EVENT_IMPACT: dict[str, list[EventImpactRecord]] = {
    "ent_company_002594": [
        EventImpactRecord(
            event_name="降息预期升温",
            impact_score=82,
            impact_level="high",
            direction="positive",
            evidence_ids=["ev_20260513_002594_macro_001"],
            workflow_run_id="wr_20260513_002594_000001",
            judgment_id="jdg_20260513_002594_001",
        ),
        EventImpactRecord(
            event_name="原材料价格波动",
            impact_score=58,
            impact_level="medium",
            direction="negative",
            evidence_ids=["ev_20260513_002594_industry_002"],
            workflow_run_id="wr_20260513_002594_000001",
            judgment_id="jdg_20260513_002594_001",
        ),
    ],
}


_WARNINGS: list[WarningRecord] = [
    WarningRecord(
        warning_id="warn_20260513_094500_001",
        time="09:45",
        title="异动预警",
        content="某板块出现放量上攻",
        severity="notice",
        related_stock_codes=["002594.SZ"],
        related_entity_ids=["ent_concept_low_altitude_economy"],
        snapshot_ids=["mkt_snap_20260513_warn_001"],
        evidence_ids=[],
    ),
]


_CONCEPTS: list[ConceptRecord] = [
    ConceptRecord(
        concept_name="低空经济",
        entity_id="ent_concept_low_altitude_economy",
        status="升温",
        heat_score=86,
        trend="warming",
        snapshot_ids=["mkt_snap_20260513_concept_low_altitude"],
        evidence_ids=[],
    ),
]


# --------------------------------------------------------------------------
# Lookup helpers — these are the only surface the service layer touches.
# --------------------------------------------------------------------------


def _normalize_stock_code(stock_code: str) -> str:
    return stock_code.upper().strip()


def find_entity_by_stock_code(stock_code: str) -> EntityRecord | None:
    norm = _normalize_stock_code(stock_code)
    for entity in _ENTITIES.values():
        if entity.stock_code and entity.stock_code.upper() == norm:
            return entity
        if entity.ticker and entity.ticker.upper() == norm.split(".")[0]:
            return entity
    return None


def search_entities(keyword: str, limit: int) -> list[EntityRecord]:
    if not keyword:
        return []
    needle = keyword.strip().lower()
    matches: list[tuple[float, EntityRecord]] = []
    for entity in _ENTITIES.values():
        haystacks = [entity.name, *(entity.aliases or [])]
        if entity.stock_code:
            haystacks.append(entity.stock_code)
        if entity.ticker:
            haystacks.append(entity.ticker)
        score = 0.0
        for hay in haystacks:
            hay_lower = hay.lower()
            if needle == hay_lower:
                score = max(score, 1.0)
            elif needle in hay_lower:
                score = max(score, 0.85)
        if score > 0:
            matches.append((score, entity))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [entity for _, entity in matches[:limit]]


def search_evidence_by_keyword(keyword: str, limit: int) -> list[EvidenceRecord]:
    needle = keyword.strip().lower()
    if not needle:
        return []
    hits: list[EvidenceRecord] = []
    for evidence in _EVIDENCE.values():
        if needle in evidence.title.lower() or needle in evidence.objective_summary.lower():
            hits.append(evidence)
        if len(hits) >= limit:
            break
    return hits


def evidence_for_entity(entity_id: str, limit: int = 20) -> list[EvidenceRecord]:
    return [e for e in _EVIDENCE.values() if e.entity_id == entity_id][:limit]


def get_evidence(evidence_id: str) -> EvidenceRecord | None:
    return _EVIDENCE.get(evidence_id)


def latest_judgment_for_entity(entity_id: str) -> JudgmentRecord | None:
    for judgment in _JUDGMENTS.values():
        if judgment.entity_id == entity_id:
            return judgment
    return None


def get_judgment_by_workflow(workflow_run_id: str) -> JudgmentRecord | None:
    for judgment in _JUDGMENTS.values():
        if judgment.workflow_run_id == workflow_run_id:
            return judgment
    return None


def get_industry_for_entity(entity_id: str) -> IndustryRecord | None:
    return _INDUSTRY.get(entity_id)


def get_event_impact(entity_id: str, limit: int) -> list[EventImpactRecord]:
    return _EVENT_IMPACT.get(entity_id, [])[:limit]


def list_index_snapshots() -> list[MarketSnapshotRecord]:
    return [snap for snap in _MARKET_SNAPSHOTS.values() if snap.kind == "index"]


def get_sentiment_snapshot() -> MarketSnapshotRecord | None:
    for snap in _MARKET_SNAPSHOTS.values():
        if snap.kind == "sentiment":
            return snap
    return None


def list_stock_snapshots(keyword: str | None = None) -> list[tuple[EntityRecord, MarketSnapshotRecord]]:
    out: list[tuple[EntityRecord, MarketSnapshotRecord]] = []
    needle = keyword.strip().lower() if keyword else None
    for snap in _MARKET_SNAPSHOTS.values():
        if snap.kind != "stock" or not snap.entity_id:
            continue
        entity = _ENTITIES.get(snap.entity_id)
        if entity is None:
            continue
        if needle:
            haystacks = [entity.name.lower(), entity.stock_code or "", entity.ticker or ""]
            if not any(needle in (h or "").lower() for h in haystacks):
                continue
        out.append((entity, snap))
    return out


def list_concepts(limit: int) -> list[ConceptRecord]:
    return _CONCEPTS[:limit]


def list_warnings(limit: int, severity: str | None) -> list[WarningRecord]:
    items = _WARNINGS
    if severity:
        items = [w for w in items if w.severity == severity]
    return items[:limit]


def now_iso() -> str:  # exposed for the service layer
    return _now_iso()
