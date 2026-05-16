"""Agent Swarm and Judge Runtime contract models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    evidence_ids: tuple[str, ...] = ()
    selection_strategy: str = "top_relevance_quality_v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(frozen=True, slots=True)
class AgentSwarmHistory:
    previous_judgment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_judgment_ids", tuple(self.previous_judgment_ids))


@dataclass(frozen=True, slots=True)
class AgentSwarmToolAccess:
    request_search: bool = True


@dataclass(frozen=True, slots=True)
class AgentSwarmInput:
    workflow_run_id: str
    ticker: str
    entity_id: str | None
    workflow_config_id: str
    evidence_selection: EvidenceSelection
    history: AgentSwarmHistory = field(default_factory=AgentSwarmHistory)
    tool_access: AgentSwarmToolAccess = field(default_factory=AgentSwarmToolAccess)


@dataclass(frozen=True, slots=True)
class SuggestedSearch:
    target_entity_ids: tuple[str, ...] = ()
    evidence_types: tuple[str, ...] = ()
    lookback_days: int | None = None
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_entity_ids", tuple(self.target_entity_ids))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))
        object.__setattr__(self, "keywords", tuple(self.keywords))


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    gap_type: str
    description: str
    suggested_search: SuggestedSearch | None = None


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    agent_run_id: str
    workflow_run_id: str
    agent_id: str
    role: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    rounds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rounds", tuple(self.rounds))


@dataclass(frozen=True, slots=True)
class AgentArgumentDraft:
    agent_id: str
    role: str
    round: int
    argument: str
    confidence: float
    referenced_evidence_ids: tuple[str, ...] = ()
    counter_evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    role_output: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "referenced_evidence_ids", tuple(self.referenced_evidence_ids))
        object.__setattr__(self, "counter_evidence_ids", tuple(self.counter_evidence_ids))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class AgentArgumentRecord:
    agent_argument_id: str
    agent_run_id: str
    workflow_run_id: str
    agent_id: str
    role: str
    round: int
    argument: str
    confidence: float
    referenced_evidence_ids: tuple[str, ...] = ()
    counter_evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    role_output: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "referenced_evidence_ids", tuple(self.referenced_evidence_ids))
        object.__setattr__(self, "counter_evidence_ids", tuple(self.counter_evidence_ids))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class RoundSummaryDraft:
    workflow_run_id: str
    round: int
    summary: str
    participants: tuple[str, ...] = ()
    agent_argument_ids: tuple[str, ...] = ()
    referenced_evidence_ids: tuple[str, ...] = ()
    disputed_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "participants", tuple(self.participants))
        object.__setattr__(self, "agent_argument_ids", tuple(self.agent_argument_ids))
        object.__setattr__(self, "referenced_evidence_ids", tuple(self.referenced_evidence_ids))
        object.__setattr__(self, "disputed_evidence_ids", tuple(self.disputed_evidence_ids))


@dataclass(frozen=True, slots=True)
class RoundSummaryRecord(RoundSummaryDraft):
    round_summary_id: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AgentSwarmRunOutcome:
    task_id: str
    status: str
    accepted_at: datetime
    agent_argument_ids: tuple[str, ...] = ()
    round_summary_id: str | None = None
    round_summary_ids: tuple[str, ...] = ()
    gaps: tuple[EvidenceGap, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_argument_ids", tuple(self.agent_argument_ids))
        object.__setattr__(self, "round_summary_ids", tuple(self.round_summary_ids))
        object.__setattr__(self, "gaps", tuple(self.gaps))


@dataclass(frozen=True, slots=True)
class JudgeToolAccess:
    get_evidence_detail: bool = True
    get_raw_item: bool = True
    query_evidence_references: bool = True
    request_search: bool = True


@dataclass(frozen=True, slots=True)
class JudgeInput:
    workflow_run_id: str
    round_summary_ids: tuple[str, ...] = ()
    agent_argument_ids: tuple[str, ...] = ()
    key_evidence_ids: tuple[str, ...] = ()
    tool_access: JudgeToolAccess = field(default_factory=JudgeToolAccess)

    def __post_init__(self) -> None:
        object.__setattr__(self, "round_summary_ids", tuple(self.round_summary_ids))
        object.__setattr__(self, "agent_argument_ids", tuple(self.agent_argument_ids))
        object.__setattr__(self, "key_evidence_ids", tuple(self.key_evidence_ids))


@dataclass(frozen=True, slots=True)
class JudgeToolCallRecord:
    tool_call_id: str
    judgment_id: str
    tool_name: str
    input: dict[str, Any]
    result_ref: dict[str, Any]
    output_summary: str
    referenced_evidence_ids: tuple[str, ...] = ()
    used_for: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "referenced_evidence_ids", tuple(self.referenced_evidence_ids))


@dataclass(frozen=True, slots=True)
class JudgmentRecord:
    judgment_id: str
    workflow_run_id: str
    final_signal: str
    confidence: float
    time_horizon: str
    key_positive_evidence_ids: tuple[str, ...] = ()
    key_negative_evidence_ids: tuple[str, ...] = ()
    reasoning: str = ""
    risk_notes: tuple[str, ...] = ()
    suggested_next_checks: tuple[str, ...] = ()
    referenced_agent_argument_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_positive_evidence_ids", tuple(self.key_positive_evidence_ids))
        object.__setattr__(self, "key_negative_evidence_ids", tuple(self.key_negative_evidence_ids))
        object.__setattr__(self, "risk_notes", tuple(self.risk_notes))
        object.__setattr__(self, "suggested_next_checks", tuple(self.suggested_next_checks))
        object.__setattr__(self, "referenced_agent_argument_ids", tuple(self.referenced_agent_argument_ids))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class JudgeRunOutcome:
    task_id: str
    status: str
    accepted_at: datetime
    judgment_id: str | None = None
    gaps: tuple[EvidenceGap, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "gaps", tuple(self.gaps))
