# Frontend Architecture

## Purpose

This frontend workspace is the customer-facing product surface for ConsensusInvest. It should be built as a Vue + Vite application that translates the core workflow protocol into a trustworthy fintech experience for end users. This workspace is intentionally separate from `docs/web_api`, which remains the backend contract source of truth.

## Product direction

- Product type: customer-facing fintech AI analysis product
- Experience style: dark, minimal, technical, high-trust
- Product structure: public landing experience plus authenticated analysis console
- Primary interaction model: workflow-first, not static report-first
- Trust model: final judgments must remain inspectable through evidence, arguments, and trace

## Frontend workspace boundaries

- `docs/web_api` defines backend communication contracts and should not become frontend implementation planning space.
- `frontend/` owns customer experience planning, frontend implementation, component architecture, and route/module structure.
- Report-style `stocks/*` and `market/*` views belong to the absorbed report module boundary and should only be integrated here when their role in the customer journey is explicit.
- The core console should treat `workflow-runs`, `events`, `snapshot`, `trace`, `evidence`, `agent-arguments`, `judgment`, and `entities` as the primary protocol surface.

## UX architecture

### 1. Dual-layer product structure

#### Public layer

The public layer sells trust, clarity, and product positioning.

Expected responsibilities:

- explain what the product does
- show why the workflow is auditable
- present workflow transparency as a differentiator
- drive users into the console or signup flow

#### Console layer

The console layer is the operational product.

Expected responsibilities:

- create and monitor workflow runs
- stream workflow progress in real time
- expose the final judgment with supporting and counter evidence
- let users inspect arguments, evidence, raw provenance, and trace structure
- support historical workflow review and entity-centric investigation

### 2. Workflow-first information architecture

The main logged-in experience should be centered on the lifecycle of a workflow run:

1. user starts a workflow run
2. UI subscribes to SSE updates
3. UI hydrates or recovers with snapshot data
4. UI reveals evidence, arguments, round summaries, and judgment as they become available
5. UI preserves traceability from conclusion back to raw source material

This means the primary console route hierarchy should start from workflow runs rather than from marketing pages or ticker summary cards.

### 3. Trust and auditability principles

The frontend must preserve the backend contract's transparency model:

- never present `judgment` as an isolated answer
- always keep visible navigation to evidence, arguments, and trace
- distinguish objective evidence from interpretive agent output
- show quality fields instead of hiding lower-quality inputs
- use workflow status and workflow stage as separate concepts in the UI

## Recommended technical architecture

## Application shell

Recommended stack direction:

- Vue 3
- Vite
- Vue Router
- Pinia for client state where shared reactive state is needed
- native `EventSource` or a thin SSE wrapper for workflow streaming
- typed API access layer generated manually from docs at first, with room for future schema automation

## Source layout

Recommended long-term folder shape:

```text
frontend/
  docs/
  src/
    app/
      router/
      providers/
      layouts/
    modules/
      landing/
      workflow-runs/
      evidence/
      judgments/
      trace/
      entities/
      settings/
    components/
      ui/
      data-display/
      trace/
    services/
      api/
      sse/
      formatters/
    stores/
    styles/
```

## Modular organization rules

Use resource-domain modularity instead of page-type sprawl.

Recommended module ownership:

- `modules/workflow-runs`: run creation, list, detail, snapshot recovery, execution state
- `modules/evidence`: evidence lists, detail, raw drill-down, references
- `modules/judgments`: final judgment presentation, judgment references, judge tool-call transparency
- `modules/trace`: layered trace graph, node drill-down, graph filters
- `modules/entities`: entity search, entity detail, entity evidence, entity relations
- `modules/landing`: public marketing pages and conversion flows

This structure should keep frontend work aligned with backend resource boundaries.

## State strategy

Use three layers of frontend state:

1. route state for page identity and filters
2. request state for queryable backend resources
3. streaming session state for active workflow event sequences

Guidelines:

- `snapshot` should be the recovery and hydration source
- SSE events should be merged incrementally and idempotently by `sequence`
- final persisted views should prefer completed resource payloads over optimistic stream deltas
- routeable objects should use canonical IDs from the API, not inferred titles

## Rendering model

Recommended screen composition for workflow detail:

- header summary with status, stage, ticker, analysis time, confidence
- central judgment panel when available
- adjacent or lower evidence and argument panels
- persistent path into trace exploration
- event activity rail for live execution and replay context

## Layered trace visualization

The trace UI should be intentionally layered instead of showing one flat graph first.

Recommended layers:

1. Judgment layer: final signal, confidence, risks, next checks
2. Argument layer: agent arguments and round summaries
3. Evidence layer: supporting and counter evidence with quality metrics
4. Provenance layer: raw items and source metadata

Interaction guidance:

- default to a simplified top-down trace path
- allow expansion into full node-edge exploration
- let users filter by source type, round, reference role, and node type
- maintain direct drill-down from graph nodes to resource detail panels

## Integration rules with backend docs

The frontend architecture must respect these contract boundaries:

- use `/api/v1/workflow-runs` as the main creation and history entry point
- use `/workflow-runs/{workflow_run_id}/events` for live updates
- use `/workflow-runs/{workflow_run_id}/snapshot` for refresh and recovery
- use `/workflow-runs/{workflow_run_id}/trace` for end-to-end reasoning overview
- use workflow-scoped evidence routes for workflow-local evidence inspection
- use `/entities/{entity_id}/evidence` for cross-workflow or entity-centric evidence access
- do not invent direct ticker-based evidence endpoints in frontend assumptions
- do not merge entity relations with evidence references in UI concepts

## Delivery priorities

Suggested implementation order for future sessions:

1. app shell, routing, theme foundation
2. landing page and product narrative
3. workflow creation and run list
4. workflow detail with SSE plus snapshot recovery
5. judgment and evidence drill-down
6. layered trace visualization
7. entity exploration

## Non-goals for this workspace plan

- no backend implementation details
- no change to the API contract docs under `docs/web_api`
- no assumption that cancel, retry, auth, or websocket are already committed backend capabilities
- no coupling of the core console to report-module-only views
