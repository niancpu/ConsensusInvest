"""Pydantic schemas for Workflow Config Web API projection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WorkflowConfigApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowConfigAgentView(WorkflowConfigApiModel):
    agent_id: str
    role: str
    stance_label: str
    thesis_label: str
    stance_output_key: str
    impact_output_key: str
    limitation: str


class WorkflowConfigView(WorkflowConfigApiModel):
    workflow_config_id: str
    debate_rounds: int
    agents: list[WorkflowConfigAgentView] = Field(default_factory=list)
