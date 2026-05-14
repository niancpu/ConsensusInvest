# Frontend Design System

## Purpose

This document defines the durable visual and interaction direction for the customer-facing frontend. The target aesthetic is a dark minimal technical fintech product with strong trust cues and clear hierarchy for complex analysis data.

## Brand principles

- serious, calm, high-signal
- technical but not intimidating
- premium without decorative excess
- transparent rather than mystical
- analytical rather than promotional

## Visual identity

### Core aesthetic

The visual direction should feel like an institutional-grade AI research console combined with a polished fintech landing page.

Core traits:

- dark-first UI
- restrained contrast palette
- dense but readable data presentation
- generous spacing around key conclusions
- subtle motion and depth, not flashy animation
- crisp typography and clear grid alignment

### Emotional goal

Users should feel:

- this system is credible
- this system is inspectable
- this system helps me reason, not just consume output

## Color system

### Base palette direction

Use a near-black graphite base instead of pure black.

Suggested palette direction:

- app background: deep graphite or blue-black
- elevated surface: slightly lighter charcoal
- border: low-contrast cool gray
- primary text: soft white
- secondary text: muted slate
- accent: restrained electric blue or cyan
- positive: controlled green
- negative: controlled red
- warning: amber
- info: cool blue

### Semantic usage

Use color to clarify state, not to carry the entire meaning.

Rules:

- `bullish` or positive signals may use green accents, but never without text labels
- `bearish` or negative signals may use red accents, but never without text labels
- evidence quality should use badges, bars, or labeled metrics rather than only hue
- trace edge types such as `supports`, `counters`, `cited`, and `refuted` should combine color, iconography, and text legend

## Typography

### Direction

Use a clean sans-serif system with a technical but modern feel.

Suggested pairing direction:

- primary UI font: modern grotesk or system sans
- numeric/data emphasis: same family with tabular numerals, or a supporting mono only where needed

### Hierarchy

Use a restrained type scale.

Recommended roles:

- display: landing hero only
- h1: major page title
- h2: major section title
- h3: card or panel title
- body: default explanatory text
- caption: timestamps, source metadata, metric labels
- mono/meta: IDs, structured values, event sequence references

### Text handling rules

- keep marketing copy concise and high-confidence
- keep analytical labels explicit and literal
- never hide key distinctions behind vague AI wording
- show canonical IDs where they aid auditability

## Layout system

### Grid principles

The layout should favor stable panels and clear scanning.

Recommended structure:

- landing: wide content sections with centered narrative blocks and product preview bands
- console: multi-column dashboard and detail layouts with fixed rhythm
- detail pages: left-to-right reading path from summary to supporting detail

### Spacing

Use consistent spacing tokens and leave breathing room around:

- judgment cards
- trace panels
- evidence detail
- event stream rows

Dense data should come from structure, not cramped spacing.

## Surfaces and containers

### Surface hierarchy

Recommended levels:

1. app background
2. base panels
3. elevated cards
4. focused or active panels
5. modal and overlay surfaces

### Styling traits

- soft borders over heavy shadows
- subtle panel elevation
- rounded corners, but not overly soft
- selective glass or translucency only if it preserves readability

## Components

### Core component families

#### Navigation

- top nav for landing
- app shell nav for console
- side nav or sectional tabs inside workflow detail
- breadcrumb or compact context header for deep drill-down

#### Data display

- metric cards
- status badges
- stage pills
- evidence cards
- argument cards
- timeline rows
- trace node cards
- JSON or payload viewer for raw items
- source metadata rows

#### Workflow interaction

- workflow creation form
- live event stream list
- snapshot recovery banner
- trace filters
- confidence and quality metric displays

#### Feedback

- skeleton loaders for streaming views
- empty-state panels
- inline error banners
- reconnect status for SSE disruption

## Interaction rules

### Motion

Motion should reinforce state changes and progressive disclosure.

Recommended use:

- soft fade or slide for event arrivals
- subtle highlight when new evidence or arguments appear
- smooth panel expansion for trace drill-down
- minimal hover and focus transitions

Avoid:

- decorative parallax
- large motion on high-frequency updates
- animation that competes with data comprehension

### Streaming behavior

The console should feel live but controlled.

Guidelines:

- stream updates into a dedicated activity rail or event area
- highlight affected sections when new data arrives
- avoid reflowing the entire page on every event
- preserve scroll stability when the user is reading detail panels

### Drill-down behavior

The user should be able to move from summary to evidence without losing context.

Recommended patterns:

- side drawers for quick inspection
- dedicated routes for full-page detail views
- persistent back-links into parent workflow context
- node selection in trace should open synchronized detail panels

## Trust-oriented UI rules

- label objective evidence separately from interpretation
- show quality fields as first-class data
- expose limitations and risk notes visibly
- keep provenance links obvious
- distinguish live stream deltas from finalized records
- avoid anthropomorphic AI framing in critical decision areas

## Accessibility and readability

- maintain strong text contrast against dark surfaces
- do not use low-contrast gray for important data
- support keyboard navigation across tables, lists, and trace interactions
- use non-color indicators for status and relationship types
- ensure charts or trace visuals have legends and accessible summaries

## Design tokens to formalize later

When implementation starts, define tokens for:

- colors
- spacing
- radii
- border styles
- typography scale
- shadows or elevation
- motion durations
- z-index layers

## MVP component priority

Create in this order:

1. app shell
2. page container and section header
3. button, input, select, badge
4. workflow status and stage indicators
5. judgment summary card
6. evidence card and evidence detail panel
7. argument card and argument detail panel
8. event stream list
9. layered trace panel
10. raw payload viewer

## Explicit anti-patterns

- do not make the console look like a generic consumer stock app
- do not overuse neon glow, glass blur, or sci-fi ornament
- do not collapse evidence quality into a single magical score
- do not visually over-celebrate final judgment while hiding its support chain
