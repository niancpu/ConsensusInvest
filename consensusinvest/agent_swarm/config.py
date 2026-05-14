"""Workflow configuration for deterministic Debate Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DebateAgentConfig:
    agent_id: str
    role: str
    stance_label: str
    thesis_label: str
    stance_output_key: str
    impact_output_key: str
    limitation: str


@dataclass(frozen=True, slots=True)
class DebateWorkflowConfig:
    workflow_config_id: str
    debate_rounds: int
    agents: tuple[DebateAgentConfig, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "debate_rounds", max(1, int(self.debate_rounds)))
        object.__setattr__(self, "agents", tuple(self.agents))
        if not self.agents:
            raise ValueError("debate workflow config must include at least one agent")


MVP_BULL_JUDGE_CONFIG = DebateWorkflowConfig(
    workflow_config_id="mvp_bull_judge_v1",
    debate_rounds=3,
    agents=(
        DebateAgentConfig(
            agent_id="bull_v1",
            role="bullish_interpreter",
            stance_label="multi-round bullish review",
            thesis_label="fundamental improvement thesis",
            stance_output_key="stance_interpretation",
            impact_output_key="bullish_impact_assessment",
            limitation="Missing full peer comparison and valuation sensitivity.",
        ),
    ),
)


DEFAULT_DEBATE_WORKFLOW_CONFIGS: Mapping[str, DebateWorkflowConfig] = {
    MVP_BULL_JUDGE_CONFIG.workflow_config_id: MVP_BULL_JUDGE_CONFIG,
}


def get_debate_workflow_config(
    workflow_config_id: str,
    configs: Mapping[str, DebateWorkflowConfig] | None = None,
) -> DebateWorkflowConfig:
    available = configs or DEFAULT_DEBATE_WORKFLOW_CONFIGS
    try:
        return available[workflow_config_id]
    except KeyError as exc:
        raise ValueError(f"unknown workflow_config_id: {workflow_config_id}") from exc

