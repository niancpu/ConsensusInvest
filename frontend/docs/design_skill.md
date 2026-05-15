---
name: frontend-design-editorial
description: Create distinctive, production-grade frontend interfaces specializing in Newspaper Typography and classic print media aesthetics. Use this skill to build news sites, editorial platforms, long-form reading apps, or any UI requiring an authoritative, classic, and highly refined typographic experience. Generates creative, polished code that avoids generic AI aesthetics.

---

This skill guides the creation of distinctive, production-grade frontend interfaces that translate traditional print media and newspaper typography into unforgettable modern web experiences. Implement real working code with exceptional attention to aesthetic details, avoiding generic "AI slop" aesthetics entirely.

## Design Thinking

Before coding, understand the context and commit to a BOLD editorial aesthetic direction:

- **Purpose**: What story or content is being presented? Is it hard news, long-form journalism, an academic paper, or a high-fashion editorial?
- **Tone**: Pick a specific editorial flavor: Classic Broadsheet (authoritative, dense), Modern Editorial Brutalism (raw, high-contrast, bold typography), Vintage Magazine (warm, textured, elegant), or Minimalist Academic (clean, spacious, highly legible). 
- **Differentiation**: What makes this reading experience UNFORGETTABLE? Is it a dramatic drop cap? An unexpected grid-breaking image? A meticulously crafted masthead?

**CRITICAL**: Execute the chosen editorial direction with precision. Whether you choose dense maximalist text columns or refined minimalist typography, the key is intentionality and classic typographic rules.

## Core Editorial Design Language

Implement these traditional print techniques using modern CSS:

1. **Masthead (报纸标题栏)**

   - High letter-spacing, uppercase, bold serif fonts.

   - Distinctive top/bottom borders (e.g., 3-4px solid black).

   - *Example*:

     ```css
     .masthead { font-size: 48px; font-weight: 900; letter-spacing: 0.2em; border-top: 3px solid #000; border-bottom: 3px solid #000; padding: 1rem 0; text-align: center; text-transform: uppercase; }
     ```

2. **Drop Cap (首字下沉)**

   - Scale the first letter 3-5x the body text size.

   - Use a distinctive emphasis color (e.g., Deep Blue #1E3A8A).

   - *Example*:

     ```css
     .drop-cap { float: left; font-size: 4.5rem; line-height: 0.85; font-weight: 900; color: #1E3A8A; margin-right: 0.15rem; margin-top: 0.1rem; }
     ```

3. **Multi-column Layout (多栏布局)**

   - Replicate classic newspaper columns for wider screens.

   - *Example*:

     ```css
     .newspaper-columns { column-count: 2; column-gap: 2rem; column-rule: 1px solid #e5e7eb; text-align: justify; }
     ```

4. **Classic Dividers (经典分隔线)**

   - Use double lines, dotted lines, or thick solid rules to separate sections, avoiding modern drop-shadow cards.

   - *Example*:

     ```css
     .section-divider { border-top: 3px double #1E3A8A; margin: 2rem 0; }
     ```

## Frontend Aesthetics Guidelines

Focus on:

- **Typography**: NEVER use generic fonts like Arial, Inter, or Roboto. Opt for distinctive Serif fonts to create traditional authority (e.g., `font-family: 'Georgia', 'Times New Roman', 'Merriweather', serif;`). Pair a dramatic display serif for headlines with a highly legible text serif for the body. Establish a strict hierarchical scale (Masthead: 3-5rem, Headline: 2-3rem, Subhead: 1.25-1.5rem, Body: 0.9375rem).
- **Color & Theme**: Commit to a classic ink-and-paper aesthetic. 
  - *Backgrounds*: Off-white/cream (`#FAF8F5`, `#F9FAFB`) to simulate paper, or stark white for modern digital news.
  - *Text*: Ink black (`#1F2937`, `#111827`) and dark grays (`#374151`).
  - *Accents*: Sharp, sophisticated accents like Deep Blue (`#1E3A8A`) or Crimson Red for Drop Caps and Dividers. NEVER use generic purple/blue tech gradients.
- **Motion**: Restraint is key. Avoid bouncy, playful animations. Use elegant, slow-fading reveals, staggered content loading (animation-delay), and subtle underline expansions on hover. Motion should feel like turning a page or focusing a lens.
- **Spatial Composition & Vertical Rhythm**: Adhere to a strict vertical rhythm. Use precise margins (e.g., `h2 { margin-top: 2rem; margin-bottom: 1rem; }`, `p { margin-bottom: 1rem; }`). Mix dense multi-column text blocks with generous negative space around hero images or pull quotes.
- **Backgrounds & Visual Details**: Add atmosphere. Implement subtle CSS grain/noise overlays (`mix-blend-mode`), paper textures, halftone patterns for images, or dramatic high-contrast photography. 

## Accessibility & Engineering Standards

- **Semantic HTML**: Use `<article>`, `<section>`, `<aside>`, `<figure>`, and `<figcaption>` to structure content meaningfully.
- **Readability**: Maintain text-to-background contrast > 7:1. Limit reading width (max line length 600-800px or use columns). Use `text-align: justify` only when column width is sufficient to avoid rivers of white space.

**IMPORTANT**: Match implementation complexity to the aesthetic vision. Elegance in editorial design comes from extreme precision in typography, spacing, and subtle texture, not from overly complex DOM structures. Interpret creatively and make unexpected choices that feel genuinely crafted for a high-end publication.