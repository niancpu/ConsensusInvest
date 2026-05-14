"""Workflow Config Web API routes."""

from __future__ import annotations

from fastapi import APIRouter

from consensusinvest.agent_swarm.config import DEFAULT_DEBATE_WORKFLOW_CONFIGS, DebateWorkflowConfig
from consensusinvest.common.response import ListPagination, ListResponse

from .schemas import WorkflowConfigAgentView, WorkflowConfigView

router = APIRouter(prefix="/api/v1", tags=["workflow_configs"])


@router.get("/workflow-configs", response_model=ListResponse[WorkflowConfigView])
def list_workflow_configs() -> ListResponse[WorkflowConfigView]:
    rows = [_config_view(config) for config in DEFAULT_DEBATE_WORKFLOW_CONFIGS.values()]
    rows.sort(key=lambda item: item.workflow_config_id)
    return ListResponse(
        data=rows,
        pagination=ListPagination(limit=len(rows), offset=0, total=len(rows), has_more=False),
    )


def _config_view(config: DebateWorkflowConfig) -> WorkflowConfigView:
    return WorkflowConfigView(
        workflow_config_id=config.workflow_config_id,
        debate_rounds=config.debate_rounds,
        agents=[
            WorkflowConfigAgentView(
                agent_id=agent.agent_id,
                role=agent.role,
                stance_label=agent.stance_label,
                thesis_label=agent.thesis_label,
                stance_output_key=agent.stance_output_key,
                impact_output_key=agent.impact_output_key,
                limitation=agent.limitation,
            )
            for agent in config.agents
        ],
    )
