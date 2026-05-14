# Frontend Pages

## Purpose

This document defines the durable page and route direction for the Vue + Vite frontend workspace. It is intended to help future sessions continue implementation without depending on prior chat context.

## Product map

The frontend should be organized into two primary surfaces:

- public landing surface
- authenticated analysis console

## 1. Public landing surface

### Landing page

Route direction:

- `/`

Primary goals:

- explain the product as an AI-assisted investment analysis platform
- show that outputs are workflow-based and auditable
- communicate the difference between evidence, arguments, and judgment
- establish a dark minimal technical brand
- drive users into the console or signup flow

Recommended sections:

1. hero section with product promise
2. trust section explaining transparent workflow reasoning
3. workflow explainer with create -> stream -> inspect -> conclude story
4. feature grid covering evidence, argumentation, judgment, and trace
5. UI preview section showing the console aesthetic
6. CTA footer

### Optional supporting marketing pages

Route direction:

- `/product`
- `/about-trust`
- `/pricing`

These should only be added if needed. The MVP can keep public content consolidated into the landing page.

## 2. Authenticated console surface

### Console home

Route direction:

- `/app`

Purpose:

- orient the user to recent activity
- provide quick entry to start a workflow run
- show recent or pinned workflow runs
- expose major product areas without overwhelming first load

Recommended panels:

- quick start workflow card
- recent runs list
- latest judgments summary
- saved entities or watchlist entry points

### Workflow run creation

Route direction:

- `/app/workflows/new`

Purpose:

- create a workflow run using backend-provided `workflow_config_id`
- capture stock code or ticker context
- allow analysis-time and source-scope configuration if the API supports it

UI rules:

- do not hardcode agent lists as the execution source of truth
- treat `workflow-configs` as the backend-owned configuration source
- present this as starting an analysis workflow, not just requesting a report

### Workflow runs list

Route direction:

- `/app/workflows`

Purpose:

- browse historical and in-progress workflow runs
- filter by ticker, status, and time range as the API allows
- open a run detail page for deeper inspection

Recommended columns or card fields:

- workflow run ID
- ticker or stock code presentation
- status
- stage when in progress
- analysis time
- created time
- final signal and confidence when completed

### Workflow run detail

Route direction:

- `/app/workflows/:workflowRunId`

This is the core product page.

Primary responsibilities:

- subscribe to SSE for live execution state
- recover state with snapshot when refreshed or re-opened
- display status and stage separately
- reveal evidence, arguments, round summaries, and judgment as they arrive
- maintain strong visibility into trace and provenance

Recommended layout:

1. top summary bar
2. central judgment or in-progress reasoning area
3. live activity/event rail
4. tabbed or split sections for evidence, arguments, rounds, and trace
5. deep links into raw items and references

Recommended tabs:

- Overview
- Evidence
- Arguments
- Rounds
- Trace
- Activity

### Workflow trace page or expanded trace mode

Route direction:

- `/app/workflows/:workflowRunId/trace`

Purpose:

- provide the most detailed layered reasoning graph
- support node filtering and drill-down
- preserve the chain from judgment to raw source

UI rules:

- start with a readable layered view, not a dense force graph
- keep detail drawers or side panels for selected nodes
- distinguish `supports`, `counters`, `cited`, and `refuted` visually

### Evidence detail page

Route direction:

- `/app/evidence/:evidenceId`

Purpose:

- show objective evidence detail
- expose quality metrics, claims, facts, raw provenance, and references
- keep interpretation separate from evidence facts

Required sections:

- source metadata
- objective summary
- key facts
- claims
- quality metrics
- raw item drill-down
- reference usage across arguments or judgment

### Raw item detail page or modal

Route direction:

- `/app/raw-items/:rawRef`

Purpose:

- expose original source material for auditability
- support folded display for large payloads
- help users validate how evidence was derived

### Agent argument detail page

Route direction:

- `/app/arguments/:agentArgumentId`

Purpose:

- show an individual argument in readable form
- expose referenced evidence, counter evidence, limitations, and role-specific output
- support back-navigation into the workflow and trace context

### Judgment detail page

Route direction:

- `/app/judgments/:judgmentId`

Purpose:

- present the final signal and reasoning cleanly
- show confidence, risk notes, next checks, and supporting/counter evidence
- expose judge tool-call transparency and link back into trace

UI rules:

- never show judgment without evidence and argument entry points
- treat it as a conclusion page with explicit audit affordances

### Entities list and search

Route direction:

- `/app/entities`

Purpose:

- search companies, industries, policies, and other supported entities
- provide cross-workflow exploration

### Entity detail

Route direction:

- `/app/entities/:entityId`

Purpose:

- show entity identity and metadata
- show entity-scoped evidence
- show entity relations separately from reasoning trace references

UI rules:

- do not blur entity relations with evidence references
- entity exploration is a complementary surface, not a replacement for workflow detail

## 3. Global experience patterns

### Navigation model

Recommended primary nav:

- Landing
- Console
- Workflows
- Entities

Recommended console secondary nav:

- Home
- New Workflow
- Workflow Runs
- Entities

### Search model

Search should support at least:

- stock code or ticker lookup for starting analysis
- workflow run lookup by ID
- entity lookup by name

### Empty states

Empty states should educate the user about the workflow model.

Examples:

- no workflow runs yet -> explain how to start the first run
- no judgment yet -> explain that the workflow is still collecting or debating
- no evidence matches -> explain filters instead of implying absence of data quality

### Error states

Error handling should map from API `error.code`, not rely only on server `message` strings.

Important cases to design for:

- `INVALID_REQUEST`
- `WORKFLOW_NOT_FOUND`
- `EVIDENCE_NOT_FOUND`
- `AGENT_ARGUMENT_NOT_FOUND`
- `JUDGMENT_NOT_FOUND`
- `BOUNDARY_VIOLATION`
- partial upstream connector failures surfaced without full workflow failure

## 4. MVP page priority

Build in this order:

1. `/`
2. `/app`
3. `/app/workflows/new`
4. `/app/workflows`
5. `/app/workflows/:workflowRunId`
6. `/app/workflows/:workflowRunId/trace`
7. `/app/evidence/:evidenceId`
8. `/app/arguments/:agentArgumentId`
9. `/app/judgments/:judgmentId`
10. `/app/entities`
11. `/app/entities/:entityId`

## 5. Explicit boundary reminders

- workflow-scoped evidence belongs under workflow run experience
- cross-workflow evidence belongs under entity experience
- report-module view APIs are not the primary organizing surface for this frontend
- `report_generation` mode must not be treated as if it yields a real `workflow_run_id` or `judgment_id`
