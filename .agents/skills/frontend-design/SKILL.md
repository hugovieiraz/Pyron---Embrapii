---
name: frontend-design
description: Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults. Use when designing web interfaces, establishing aesthetic directions, creating landing pages, or redesigning UI to avoid generic AI clichés.
license: Complete terms in LICENSE.txt
---

# Frontend Design

Approach this as the design lead at a design studio known for giving every client a distinct visual identity that is not mistaken for anyone else's. This client has already rejected proposals that felt cliché or templated, and is paying for a distinctive point of view: make deliberate, opinionated choices about palette, typography, and layout that are specific to this brief, and take aesthetic risk if justified.

---

## 🎯 Ground Your Designs in the Subject Matter

If the brief does not identify what the product or subject matter is, identify it yourself before designing, and confirm with the client. You can come up with one concrete subject, the design's audience, and the design's primary job, as a proposal.

If there's any information in your memory about the client's preferences or context about what they're building, use that as a hint. The subject's industry, subject matter, materials, and vernacular are where distinctive visual choices come from — a design for a toy for girls aged 8–11 will be very aesthetically different from a dashboard for financial analysts. Build with the brief's real content and subject matter throughout.

---

## 🎨 Design Principles

### 1. Hero & First Impression
For web designs, the hero is the first thing viewers will see. Open with the most characteristic thing in the subject's world, in the form that is most appropriate: a headline, an image, an animation, a live demo, an interactive moment, or other treatments. Be deliberate with your choice: a big number with a small label, supporting stats, and a gradient accent is the default treatment, so only use it if that's truly the best option.

### 2. Typography Carries Personality
Typography carries the personality of the page. You don't need a different typeface for display or headline text and body content: use one family or two, and if two, make them clearly distinct.

Choose your typefaces deliberately, not the default families you would reach for on any other project, and set a clear type scale following the default guidance of *The Elements of Typographic Style* with intentional weights, widths, and spacing. When type is used as a headline or visual element, use the type treatment itself as an active part of the design, not a neutral delivery vehicle for the content.

- Default to line lengths of less than 80 characters.
- Serif typefaces can have slightly longer line lengths; give serif body text slightly more line-height than a sans-serif.

#### Typographic Anti-Patterns to Avoid:
These are the commonest tells of an automated/templated page:
- **Accenting just a single word or phrase in a headline**, like putting one word in italic/bold or a different color.
- **Using all caps for labels indiscriminately**.
- **Adding unnecessary typographic labels or eyebrows above content**.

### 3. Visual Structure is Information
Structural devices like outlines, borders, numbering, eyebrows, dividers, labels, etc., encode useful information about the content rather than decorate it.
- Many generic designs use numbered markers (`01` / `02` / `03`), but that's only appropriate if the content actually is a sequence — like a stepped process or a timeline.
- Before adding numbered markers, check whether the content really is a sequence.

### 4. Intentional Motion
Use non-user-triggered motion sparingly and deliberately, only to draw attention.
- A single orchestrated moment — one page-load sequence or one reveal — lands better than scattered effects.
- Fade-and-slide-up entrances on each section and hover transitions on every card are the generic default and read as AI-generated.
- Motion that answers a person's action (opening, expanding, confirming) is welcome when it shows what changed.

---

## 🚨 Process: Plan, Review Against the Brief, Build, Critique

### The 5 Tell-Tale AI Design Clichés (Calibration)
AI-generated design right now clusters around predictable traits:
1. **Warm cream background** (near `#F4F1EA`) with high-contrast serif display and a terracotta or warm-clay accent (often near `#D97757`).
2. **Near-black background** with a single bright acid-green or vermilion accent.
3. **Broadsheet-style layout** with hairline rules, zero border-radius, and dense newspaper-like columns.
4. **The SaaS-card kit**: content chopped into identical rounded cards, one border-radius on everything regardless of hierarchy, the same soft grey shadow (`rgba(0,0,0,.1)`) under each, and gradient washes as decoration.
5. **Template chrome** that appears whatever the subject: a tracked-out ALL-CAPS eyebrow label above every heading; meta strings joined with middle dots (`'A · B · C'`); labels built as `'WORD — fragment'` with a spaced em dash; tinted near-black (`#0B0B0B`, `#111`) standing in for black; a monospace face for small data labels; a `→` appended to link and button text.

> **Rule:** All traits are legitimate for some briefs, but they are defaults rather than choices. Where the brief pins down a visual direction, follow it exactly. Where it leaves an axis free, **do not spend that freedom on one of these defaults**.

---

### Two-Pass Execution Workflow

1. **Pass 1 — Design Plan & Token System:**
   Brainstorm a short design plan based on the client's brief:
   - **Color:** Describe the core base palette as 4–6 named hex values tied to the subject.
   - **Type:** The typefaces and their specific roles.
   - **Layout:** Layout concept, using one-sentence prose descriptions and ASCII wireframes to ideate and compare. Include alignment guidance (left-aligned, center-aligned, justified).
   - **Principles:** High-level guidance for what makes this page uniquely suited for this brief.

2. **Pass 2 — Critique & Build:**
   Review the plan against the brief before writing code:
   - If any part of it reads like the generic default you would produce for any other project, revise that part. Say what you changed and why.
   - When writing CSS/Tailwind, be careful of selector specificities and conflicting utility margins/paddings between sections.

---

## ⚖️ Restraint and Self-Critique

Spend your boldness in one place. Let one element be the memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief.

Build to an uncompromised quality floor:
- Responsive down to mobile viewports.
- Visible keyboard focus states (`:focus-visible`).
- Respect `prefers-reduced-motion`.
- Visually accessible color contrast (WCAG AA).
- Harmonious color palettes.

*Take Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory.*

---

## ✍️ Copywriting & Voice in Design

Words appear in a design for one reason: to make it easier to understand and use. They are design content, not decoration. Bring the same intentionality and minimalism to copywriting that you would bring to spacing and color.

1. **Write from the End-User's Perspective:**
   - Name things by what users understand in simple language, not by system architecture (e.g., "Notification preferences" instead of "Webhook dispatch config").
   - Describe what something is or does in plain terms rather than trying to oversell. Specificity and legibility beat cleverness.
2. **Use Active Voice as Default:**
   - CTAs must state exactly what happens when clicked: "Save changes", not "Submit".
   - Maintain vocabulary continuity across flows: the button that says "Publish" produces a notification that says "Published".
3. **Empty States & Errors as Direction, Not Mood:**
   - Explain what went wrong and how to fix it in the product's voice, not a person's. Errors don't apologize; they guide clearly.
   - An empty screen is an invitation to act, not a dead end.
4. **Conversational, Disciplined Tone:**
   - Plain verbs, sentence case, no filler text. Match tone to the brand and audience. Each written element must do exactly one job.

---

## 📌 Checklist de Validação de Direção de Arte

Antes de aprovar ou entregar o design da interface, confirme:

- [ ] O conceito visual reflete a identidade específica do tema ou cliente, em vez de recorrer a templates genéricos?
- [ ] Foram evitados os 5 clichês de IA (cards idênticos em série, gradientes arbitrários, falso broasheet, ALL-CAPS tracked out sem propósito)?
- [ ] A tipografia possui escala bem definida e peso intencional, sem recorrer ao artifício de colorir/grifar apenas uma palavra isolada no título?
- [ ] A estrutura visual (linhas, números, divisores) comunica significado real (como etapas sequenciais) em vez de enfeite?
- [ ] A interface possui apenas um ponto focal de ousadia estética, mantendo o restante disciplinado e funcional?
- [ ] O microcopy é ativo, claro e consistente com as ações do usuário?
