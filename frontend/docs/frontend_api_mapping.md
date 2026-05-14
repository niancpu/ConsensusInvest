# Frontend API Mapping

## Purpose

This document maps the frontend product surfaces to the backend API contract documented under `docs/web_api`. It exists to keep future frontend implementation aligned with the real protocol and to prevent accidental boundary drift.

## Source of truth

The backend contract source of truth remains:

- `docs/web_api/endpoints.md`
- `docs/web_api/overview.md`
- `docs/web_api/workflow.md`
- `docs/web_api/evidence.md`
- `docs/web_api/agents_judgments.md`
- `docs/web_api/entities.md`
- `docs/web_api/appendix.md`

This document is a frontend consumption guide, not a replacement API spec.

## Core response assumptions

Frontend data access should assume the unified response shape documented in `overview.md`:

- success: `data` plus `meta`
- list: `data` plus `pagination` plus `meta`
- error: `error` plus `meta`

Do not reintroduce the old `code/message/data` response wrapper into frontend planning for the core protocol.

## Primary frontend-to-API map

## 1. Workflow creation and configuration

### Workflow config discovery

Frontend usage:

- populate workflow creation UI
- describe available run modes and labels

Endpoint:

- `GET /api/v1/workflow-configs`

Important rules:

- use backend-returned `workflow_config_id`
- do not hardcode agent lists as the authoritative execution model

### Start workflow run

Frontend usage:

- submit the analysis form
- create an auditable workflow-first session

Endpoint:

- `POST /api/v1/workflow-runs`

Expected frontend follow-up:

1. store returned `workflow_run_id`
2. open SSE on `events_url`
3. fetch or recover from `snapshot_url` when needed

Important rules:

- treat the `202 Accepted` response as queued work, not a completed result
- preserve `analysis_time` as a real user-selected or backend-relevant value

## 2. Workflow browsing and detail

### Workflow run list

Frontend usage:

- recent runs page
- dashboard recent activity

Endpoint:

- `GET /api/v1/workflow-runs`

Use for:

- concise historical summaries
- filtering by ticker and status

Do not use for:

- full reasoning replay
- evidence-level inspection

### Workflow run detail

Frontend usage:

- summary header for a run
- in-progress lifecycle state

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}`

Use fields such as:

- `status`
- `stage`
- `analysis_time`
- `workflow_config_id`
- `progress`
- `links`

Important rules:

- `status` is lifecycle state
- `stage` is current execution phase
- the UI must not collapse these into one ambiguous label

### Workflow snapshot

Frontend usage:

- page reload recovery
- reconnect recovery after SSE interruption
- historical hydration

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/snapshot`

Important rules:

- snapshot is recovery and hydration, not the live streaming channel
- merge snapshot carefully with local streamed state
- compare local event sequence with `last_event_sequence`

### Workflow trace

Frontend usage:

- layered reasoning overview
- trace page and drill-down graph

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/trace`

Important rules:

- trace is the graph overview, not the full raw detail payload
- use resource detail endpoints for expanded panels

## 3. SSE event model

### Live workflow stream

Frontend usage:

- real-time activity rail
- incremental UI updates during workflow execution

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/events`

Critical frontend behavior:

- process events idempotently by `sequence`
- support reconnection using `after_sequence` or `Last-Event-ID`
- treat deltas as incremental display data until finalized resource payloads arrive

Important event families to surface:

- workflow lifecycle events
- raw item collected
- evidence normalized and structured
- agent argument delta and completed
- round summary delta and completed
- judge tool call started and completed
- judgment delta and completed

Important rules:

- live event UI should not replace resource detail views
- judge tool calls are part of the transparency model and should remain visible
- `report_generation` and non-workflow async tasks must not be modeled as if they stream through this workflow SSE channel

## 4. Evidence and provenance

### Workflow-scoped evidence list

Frontend usage:

- workflow detail evidence tab
- supporting and counter evidence browsing within one run

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/evidence`

Display guidance:

- show `source_quality`, `relevance`, `freshness`, and `structuring_confidence` separately
- do not convert them into one opaque score

### Evidence detail

Frontend usage:

- evidence detail page or drawer
- source inspection and auditability

Endpoint:

- `GET /api/v1/evidence/{evidence_id}`

Important rules:

- evidence is objective only
- do not label evidence itself as bullish or bearish
- interpretation belongs to arguments and judgment

### Evidence structure

Frontend usage:

- show how evidence was structured from source material

Endpoint:

- `GET /api/v1/evidence/{evidence_id}/structure`

### Evidence raw source

Frontend usage:

- provenance drill-down from evidence to raw item

Endpoint:

- `GET /api/v1/evidence/{evidence_id}/raw`

### Evidence references

Frontend usage:

- show where this evidence was used in the reasoning chain

Endpoint:

- `GET /api/v1/evidence/{evidence_id}/references`

### Workflow-wide evidence references

Frontend usage:

- build graph overlays or reference maps for a workflow

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/evidence-references`

Important rules:

- evidence references model reasoning links
- they are not the same as entity relations

### Raw item detail

Frontend usage:

- deepest provenance inspection
- debug and audit source inputs

Endpoint:

- `GET /api/v1/raw-items/{raw_ref}`

UI rules:

- large payloads should be collapsible
- raw detail should usually be a drill-down view, not a default expanded section

## 5. Arguments, rounds, and judgment

### Agent runs

Frontend usage:

- execution metadata
- supporting context around arguments

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/agent-runs`

### Agent arguments list

Frontend usage:

- workflow detail argument panel
- round and agent filtered reasoning review

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/agent-arguments`

Important rules:

- use common fields first for shared UI
- treat `role_output` as role-specific and potentially variable by agent

### Agent argument detail

Frontend usage:

- dedicated argument page or side panel

Endpoint:

- `GET /api/v1/agent-arguments/{agent_argument_id}`

### Agent argument references

Frontend usage:

- highlight supporting and counter evidence for a single argument

Endpoint:

- `GET /api/v1/agent-arguments/{agent_argument_id}/references`

### Round summaries

Frontend usage:

- workflow navigation layer between raw arguments and final judgment

Endpoints:

- `GET /api/v1/workflow-runs/{workflow_run_id}/round-summaries`
- `GET /api/v1/round-summaries/{round_summary_id}`

Important rules:

- round summary is a navigation aid, not a new factual layer
- argument and evidence detail remain authoritative when there is tension

### Workflow judgment

Frontend usage:

- primary conclusion panel on workflow detail

Endpoint:

- `GET /api/v1/workflow-runs/{workflow_run_id}/judgment`

### Judgment detail

Frontend usage:

- dedicated judgment view and drill-down

Endpoint:

- `GET /api/v1/judgments/{judgment_id}`

### Judgment references

Frontend usage:

- supporting and counter evidence sections on judgment view

Endpoint:

- `GET /api/v1/judgments/{judgment_id}/references`

### Judge tool calls

Frontend usage:

- transparency section showing judge audit behavior

Endpoint:

- `GET /api/v1/judgments/{judgment_id}/tool-calls`

Important rules:

- do not frame tool calls as private chain-of-thought
- present them as auditable retrieval and validation steps

## 6. Entity exploration

### Entity list

Frontend usage:

- search and browse entities

Endpoint:

- `GET /api/v1/entities`

### Entity detail

Frontend usage:

- entity profile page

Endpoint:

- `GET /api/v1/entities/{entity_id}`

### Entity evidence

Frontend usage:

- cross-workflow or entity-centric evidence exploration

Endpoint:

- `GET /api/v1/entities/{entity_id}/evidence`

Critical boundary:

- use this route for cross-workflow evidence access
- do not invent direct ticker-based evidence querying in frontend assumptions

### Entity relations

Frontend usage:

- semantic relationship view between entities

Endpoint:

- `GET /api/v1/entities/{entity_id}/relations`

Critical boundary:

- entity relations are not evidence references
- do not merge these two models in frontend graph design

## 7. Error and state mapping

Frontend handling should explicitly map API state enums from `appendix.md`.

Important enums:

- workflow status: `queued`, `running`, `completed`, `failed`, `cancelled`
- workflow stage: `queued`, `collecting_raw_items`, `normalizing_evidence`, `structuring_evidence`, `debate`, `round_summary`, `judge`, `completed`, `failed`
- reference role: `supports`, `counters`, `cited`, `refuted`
- report mode: `report_generation`, `with_workflow_trace`
- data state: `ready`, `partial`, `missing`, `refreshing`, `stale`, `failed`

Important error codes to map in UI:

- `INVALID_REQUEST`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `WORKFLOW_NOT_FOUND`
- `RAW_ITEM_NOT_FOUND`
- `EVIDENCE_NOT_FOUND`
- `AGENT_ARGUMENT_NOT_FOUND`
- `JUDGMENT_NOT_FOUND`
- `BOUNDARY_VIOLATION`
- `CONNECTOR_FAILED`
- `AGENT_FAILED`
- `JUDGE_FAILED`
- `INTERNAL_ERROR`

## 8. Explicit non-assumptions

Frontend implementation must not assume the following unless backend docs are updated:

- cancellation exists
- retry exists
- websocket exists
- auth behavior is finalized
- report generation produces a real workflow run or judgment

## 9. Recommended first integration slice

Build frontend API integration in this order:

1. `GET /api/v1/workflow-configs`
2. `POST /api/v1/workflow-runs`
3. `GET /api/v1/workflow-runs`
4. `GET /api/v1/workflow-runs/{workflow_run_id}`
5. `GET /api/v1/workflow-runs/{workflow_run_id}/events`
6. `GET /api/v1/workflow-runs/{workflow_run_id}/snapshot`
7. `GET /api/v1/workflow-runs/{workflow_run_id}/judgment`
8. `GET /api/v1/workflow-runs/{workflow_run_id}/evidence`
9. `GET /api/v1/workflow-runs/{workflow_run_id}/trace`
10. deeper detail endpoints for evidence, arguments, judgment, and entities
