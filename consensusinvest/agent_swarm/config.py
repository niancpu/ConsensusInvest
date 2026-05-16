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
    deterministic_interpretation: str
    impact_adjustment: float = -0.08


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
            stance_label="多轮偏多复核",
            thesis_label="基本面改善假设",
            stance_output_key="stance_interpretation",
            impact_output_key="bullish_impact_assessment",
            limitation="缺少完整同业对比和估值敏感性验证。",
            deterministic_interpretation="证据整体支持当前投资假设，但结论必须能通过证据引用回查。",
            impact_adjustment=-0.08,
        ),
        DebateAgentConfig(
            agent_id="bear_v1",
            role="bearish_reviewer",
            stance_label="审慎反方复核",
            thesis_label="风险约束与反向证据假设",
            stance_output_key="risk_interpretation",
            impact_output_key="bearish_risk_assessment",
            limitation="反方判断仍缺少完整现金流、负债结构和行业景气度交叉验证。",
            deterministic_interpretation="证据虽可支撑部分正向叙事，但仍需优先核对现金流质量、估值压力和反向证据。",
            impact_adjustment=0.04,
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
