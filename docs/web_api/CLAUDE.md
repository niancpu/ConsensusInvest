# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository scope

This directory is documentation for the core Web API contract at `docs/web_api`, not an application code package. It defines the backend-to-frontend protocol for the main analysis workflow and should stay focused on communication contracts rather than implementation details.

## Development commands

There is no build, lint, or test toolchain in this directory at present. Common work here is editing Markdown API specs directly.

## Architecture overview

### Document roles

- `endpoints.md` is the index and reading order for the API docs. Start there when orienting yourself.
- `overview.md` defines cross-cutting protocol rules: API scope, JSON envelope shape, common IDs, time formatting, and the boundary with the absorbed report module.
- `workflow.md` defines the main async analysis flow centered on `workflow-runs`: task creation, status/detail, snapshot recovery, trace inspection, and SSE event streaming.
- `evidence.md` defines the evidence pipeline resources and boundaries: `raw-items` -> `evidence` -> `evidence structure` -> `references`.
- `agents_judgments.md` defines the reasoning layer built on top of evidence: agent runs, agent arguments, round summaries, final judgment, and judgment/evidence references.
- `entities.md` defines cross-workflow entity resources and entity relations. Use this for entity-centric evidence access; do not add ticker-based evidence shortcuts that bypass workflow/entity boundaries.
- `appendix.md` holds shared enums, config discovery, error codes, and explicit MVP decisions / non-decisions.

### Big-picture protocol model

The core system is an auditable async analysis workflow:

1. A client creates a workflow run with `POST /api/v1/workflow-runs`.
2. Runtime progress is observed through SSE on `/workflow-runs/{workflow_run_id}/events`.
3. Snapshot/state recovery uses `/workflow-runs/{workflow_run_id}/snapshot`.
4. Final conclusions are never standalone: they must trace back through `judgment` -> `agent arguments` -> `evidence` -> `raw items`.
5. `/workflow-runs/{workflow_run_id}/trace` is the explicit end-to-end reasoning graph for that audit chain.

When editing docs, preserve this transparency requirement: the API is designed so conclusions remain inspectable and replayable, not as opaque one-shot report generation.

### Key modeling rules

- `Evidence` is objective only. It stores facts, extracted claims, and quality metrics, but not bullish/bearish interpretation.
- Interpretive stance belongs in `Agent Argument` and `Judgment`, which must retain explicit evidence references.
- Low-quality, partial, or conflicting information should remain visible as structured fields rather than being hidden.
- `snapshot` is for recovery/history hydration; SSE is the live incremental channel.
- `status` describes lifecycle, while `stage` describes current execution phase.

### Boundary with the report module

A major architectural constraint across these docs is the separation between the core workflow protocol in `docs/web_api` and the absorbed report/view module documented elsewhere.

- `docs/web_api` owns the main workflow resources: workflow runs, trace, evidence, agents, judgments, entities.
- Report-style `stocks/*` and `market/*` view APIs are documented under `docs/report_module`, not here.
- Legacy `analysis/*` and `reports/*` test APIs are intentionally removed rather than kept as compatibility aliases.
- The unified response shape in this repo is `data/meta/error`; do not reintroduce the older `code/message/data` wrapper from the absorbed module into the core protocol docs.
- `report_generation` mode returns `report_run_id` and must not imply a real `workflow_run_id` or `judgment_id`.
- Report views may consume workflow outputs and evidence, but they do not replace the core workflow.

### Query-boundary rules that matter

- Workflow-scoped evidence access lives under `/workflow-runs/{workflow_run_id}/...`.
- Cross-workflow or entity-centric evidence access lives under `/entities/{entity_id}/evidence`.
- Do not add direct ticker-based evidence query endpoints that blur workflow/entity boundaries.
- Do not mix entity relations with evidence references: entity relations model semantic relationships between entities, while evidence references model reasoning/audit links in the inference chain.

### Config and capability assumptions

- Workflow creation should use backend-provided `workflow_config_id` values from `/api/v1/workflow-configs`; do not hardcode agent lists as the source of truth.
- MVP assumptions explicitly documented here include async `202 Accepted` creation, SSE for live updates, HTTP JSON for queries, and no default WebSocket support.
- Cancellation/retry/auth are not committed capabilities unless the docs are explicitly updated to add them.

## Editing guidance for this repository

- Keep docs concise and contract-focused; avoid turning them into frontend page specs or backend implementation notes.
- Preserve the reading-order split across files instead of collapsing all resources into one large document.
- When adding endpoints or fields, update the relevant resource doc and ensure any shared enums, errors, or boundary decisions remain consistent with `appendix.md` and `overview.md`.
- If a change affects auditability or module boundaries, verify it stays consistent across `overview.md`, `workflow.md`, `evidence.md`, and `agents_judgments.md`.
