---
name: cala-brand-guidelines
description: >-
  Design, build, or restyle websites, landing pages, agentic data explorers,
  interactive reports, documentation, and product marketing surfaces in the
  official CALA.AI brand aesthetic. Use whenever the user mentions Cala,
  cala.ai, warm editorial agentic UI, or wants a design combining Cala's
  parchment-and-espresso palette, Tiempos editorial serif headings, tactile
  query pills, structured data storytelling, and hand-drawn ink SVG accents.
---

# Design Web Surfaces Like CALA.AI

Act as a principal CALA.AI brand designer, editorial art director, information architect, and design engineer. Turn technical infrastructure, structured knowledge graphs, benchmarks, pricing, and agentic workflows into interfaces that feel **verified, tactile, human, and effortlessly clear**.

## Brand Context & Philosophy: "Warm Editorial Precision"

Cala is the verified knowledge graph for AI agents (*"Skip the data"*, *"So agents query knowledge, not chaos"*). Its visual identity bridges two worlds that rarely meet:

1. **Architectural Structural Clarity:** Generous breathing room on a single continuous canvas, disciplined typographic hierarchy, high-signal data visualizations, zero decorative gradients or glows, and immediate comprehension of proof and metrics.
2. **Warm Print-Editorial Craft & Hand-Drawn Ink:** Rather than stark clinical `#ffffff`/`#000000` monochrome, Cala prints **deep espresso ink (`#2e2723`) on warm sand parchment (`#f6e8cd`)**, pairs light high-contrast editorial serifs (**Tiempos Headline**) with neo-grotesque UI sans (**Waldenburg**), and punctuates key moments with **hand-sketched charcoal rules, expressive scribble strikethroughs, wavy ink underlines, and vintage stippled illustrations**.

The contrast *is* the brand message: **messy human chaos goes in; clean, verified, structured data comes out.**

### Core Brand Pillars at a Glance

| Dimension | CALA.AI Brand Standard |
| :--- | :--- |
| **Canvas & Ink** | Warm sand `#f6e8cd` canvas, translucent cream `#fcf8f0` cards, deep espresso `#2e2723` ink |
| **Heading Voice** | **Tiempos Headline Light** (`400`, serif), literary, airy, and authoritative |
| **Eyebrows & Units** | Signature `12px uppercase tracking-[0.2em]` + colored dot on KPIs; `11px` tracked stat units; `tracking-widest` tier labels |
| **Accents** | Curated editorial ink accents: **Gold `#ffc234`**, **Sky `#30bfff`**, **Orchid Pink `#efdcf2`/`#9f53a6`** |
| **Graphic Soul** | **Hand-drawn SVG ink rules, scribble strikethroughs, wavy underlines, and stippled `1.2em` heading icons** |
| **Tactile Controls** | Translucent parchment cards, solid `#2e2723` pill tabs, and **2px hard-offset keycap query tokens** |

---

## Priority Order

When requirements compete, protect them in this order:

1. **Preserve factual accuracy:** Keep supplied metrics, schemas, API endpoints, MCP configs, units, and claims exact.
2. **Preserve host stack & conventions:** Adapt seamlessly to React/Next.js, Tailwind v4, Vue, Astro, or standalone HTML/CSS without forcing a rewrite.
3. **Lead with contrast & proof:** Frame the chaos-vs-clarity argument immediately—pair bold editorial statements with concrete interactive or structured proof (query chains, charts, dark `mcp.json` blocks, or KPI deltas).
4. **Enforce unmistakable Cala materiality:** Maintain the `#f6e8cd` / `#fcf8f0` / `#2e2723` surface hierarchy, serif-display + sans-UI pairing, and organic SVG ink accents.
5. **Maintain calm pacing:** Let open parchment space carry the hierarchy. Never crowd sections with nested boxes, drop shadows, or SaaS bloat.

---

## Authoritative Visual System

For drop-in CSS custom properties and component classes, link or adapt [assets/cala-brand.css](./assets/cala-brand.css). For hand-drawn SVG ink dividers, scribbles, underlines, and illustration guidelines, read [references/svg-ink-and-motifs.md](./references/svg-ink-and-motifs.md).

### 1. Color Architecture & Tokens

Never use raw `#000000` for surfaces or `#ffffff` as a page background. White (`#ffffff`) is reserved strictly for text inside dark code blocks, primary button labels, or subtle translucent glass overlays (`bg-white/25 backdrop-blur-md`).

#### Warm Parchment Surfaces (Beige Scale)
* **Page Canvas (`--cala-beige` / `--cala-bg`):** `#f6e8cd` — Continuous root background for `<body>` and fixed navbar.
* **Elevated Cream (`--cala-beige-50`):** `#fcf8f0` — Used at `60%` opacity (`#fcf8f099` / `bg-beige-50/60`) for bento cards and chart containers so surfaces feel softly integrated into the parchment, or solid `#fcf8f0` for dropdown menus and light text/buttons on dark espresso cards.
* **Warm Sand Container (`--cala-beige-200`):** `#f1dbb7` — Used at `60%` opacity (`bg-beige-200/60`) for secondary feature containers (e.g., Free tier pricing card).

#### Espresso Ink & Structural Scale (Brown Scale)
* **Primary Ink & Dark Surface (`--cala-brown`):** `#2e2723` — Headings, primary text, solid CTA buttons, active pill/vertical tabs, code terminal background, and high-contrast Enterprise cards.
* **Foreground (`--cala-brown-900`):** `oklch(32% .015 54.05)` (`#39312c`) — Default body text token.
* **Dark Hover / Terminal Border (`--cala-brown-800`):** `oklch(38.8% .018 50.44)` — Button hover state, secondary lead prose, code header border.
* **Icon Ink (`--cala-brown-700`):** `oklch(46.7% .021 53.63)` — Taxonomy card icons, muted terminal window dots (`60%` opacity).
* **Muted Copy (`--cala-brown-600`):** `oklch(54.4% .025 51.26)` — Section subtitles, bento card descriptions, inactive tab labels.
* **Muted UI / Focus Ring (`--cala-brown-500`):** `oklch(62.4% .028 52.01)` — Scroll prompts, accordion chevrons, focus rings.
* **Subtle Caption (`--cala-brown-400`):** `oklch(70% .032 49.31)` — Italic chart unit labels (`Net Income / Loss ($B)`), code filenames (`mcp.json`).
* **Card Hairline (`--cala-brown-200`):** `oklch(84.6% .02 50.14)` (`#d8c9c1`) — Crisp `1px` borders on cream bento cards (`border-brown-200`) or `40%` opacity on chart frames (`border-brown-200/40`).
* **Translucent Ink Washes:**
  * `rgba(46, 39, 35, 0.05)` (`bg-brown/5`): KPI metric card fill and dropdown hover states.
  * `rgba(46, 39, 35, 0.10)` (`bg-brown/10`): `1px` hairline grid dividers (`gap-px`) and outline button hover states.

#### Functional & Data Accents
Use color intentionally to spotlight primary value propositions, live metrics, and typed query syntax:
* **Cala Gold (`--cala-yellow`):** `#ffc234` (Scale: `100: #fff3c6`, `200: #ffe488`, `300: #ffd14a`). Used for high-intent primary CTAs (`Try it`), rotating hero verbs (`verify`, `clean`), and efficiency KPIs (`8x`). Always pair `#ffc234` button fills with `#2e2723` dark brown text (never white text on yellow).
* **Cala Sky Blue (`--cala-blue`):** `#30bfff` (Scale: `100: #dff2ff`, `200: #b8e7ff`, `300: #78d5ff`, `500: #06a8f1`, `600: #0086ce`, `700: #006ba7`). Used for accuracy KPIs (`+7.66pp`), primary chart series lines/dots, `NEW` badges (`bg-blue-400 text-brown`), and query entity tokens (`bg-blue-100 text-blue-700`).
* **Operator Orchid Pink (`--cala-pink`):** `#e1bee6` (`200: #efdcf2`, `500: #ba72c3`, `600: #9f53a6`). Used inside structured query tokens to distinguish operators (`=`) and literal filter values (`2016`, `2026`).
* **Warm Coral (`--cala-orange`):** `#fb6f3f` — Secondary data series or alert accent when a third semantic hue is required.

---

### 2. Typography & Hierarchy

Cala relies on a strict three-voice typographic system (plus monospace for code). When Cala's commercial webfont files (`Tiempos Headline`, `KMR Waldenburg`, `ABC Stefan`) are not hosted in the project, load the Google Fonts optical equivalents below:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Architects+Daughter&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:ital,wght@0,400..600;1,400..500&display=swap" rel="stylesheet">
```

* **Editorial Display Serif (`--font-tiempos`):** `'tiempos', 'Tiempos Headline', 'Instrument Serif', Georgia, serif`
  * **Crucial Rule:** Always set at **Regular weight (`400`)**, never bold (`700`). Its elegance comes from sharp high-contrast strokes at large scale with tight leading and tracking.
* **UI & Prose Sans (`--font-sans`):** `'waldenburg', 'KMR Waldenburg', 'Plus Jakarta Sans', system-ui, sans-serif`
  * Clean neo-grotesque at `400`/`500` for body copy, navigation, tabs, and buttons; `600` (`font-semibold`) for compact card titles and micro-badges.
* **Hand-Lettered Callout (`--font-stefan`):** `'Stefan-Simple', 'ABC Stefan Simple', 'ABC Stefan Simple Trial', 'Architects Daughter', serif`
  * **Local & Bundled Loading:** `ABC Stefan Simple` is configured via `@font-face` in [assets/cala-brand.css](./assets/cala-brand.css) to detect OS-installed copies (`local("ABC Stefan Simple")`, `local("ABC Stefan Simple Trial")`) or load from `assets/fonts/ABCStefan-Simple.woff2` (or `.otf`/`.ttf`).
  * **Crucial Glyph Rule:** Write text in natural sentence/lowercase (`out of reach.`, `The expertise was always there.`) without `text-transform: uppercase`—`ABC Stefan Simple` natively renders hand-drawn capital forms with distinct uppercase/lowercase glyph alternates so repeated letters look genuinely hand-lettered.
  * **Extreme Restraint:** Use at most 1–2 times on an entire page to humanize a narrative pivot, paired with a hand-drawn SVG underline or scribble. Never use for UI controls or paragraphs.
* **Code & Identifiers (`--font-mono`):** `'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`
  * Used strictly inside `#2e2723` dark code blocks (`mcp.json`, CLI commands, JSON schemas).

#### Exact Type Scale & Roles

| Role | Font Stack | Mobile Size | Desktop (`md` / `lg`) | Weight | Line Height | Tracking |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Hero Litany** | `--font-tiempos` | `10.5cqw` | `7.5cqw` | `400` | `1.0` | `normal` |
| **Display Statement (`h1`)** | `--font-tiempos` | `3rem` (`48px`) | `clamp(4.5rem, 8vw, 7.75rem)` | `400` | `1.1` | `-0.025em` |
| **Section Title (`h2`)** | `--font-tiempos` | `1.875rem` (`30px`) | `3rem` (`48px`) / `3.75rem` (`60px`) | `400` | `1.2` (`tight`) | `-0.025em` |
| **Manifesto Stanza** | `--font-tiempos` | `1.5rem` (`24px`) | `2.25rem` (`36px`) / `3rem` (`48px`) | `400` | `1.25–1.375` | `-0.015em` |
| **KPI Metric Value** | `--font-tiempos` | `2.25rem` (`36px`) | `3.75rem` (`60px`) | `400` | `1.0` | `-0.025em` (`tabular-nums`) |
| **Pricing Card Title (`h3`)** | `--font-tiempos` | `1.875rem` (`30px`) | `2.25rem` (`36px`) | `400` | `1.25` | `-0.025em` |
| **Accordion Question (`h3`)** | `--font-tiempos` | `1.25rem` (`20px`) | `1.875rem` (`30px`) | `400` | `1.25` | `normal` |
| **Section Subtitle** | `--font-sans` | `1rem` (`16px`) | `1.125rem` (`18px`) / `1.25rem` (`20px`) | `400–500` | `1.625` (`relaxed`) | `normal` |
| **Body / Lead Copy** | `--font-sans` | `0.875rem` (`14px`) | `1rem` (`16px`) | `400–500` | `1.625` (`relaxed`) | `normal` |
| **Bento Card Title (`h3`)** | `--font-sans` | `0.875rem` (`14px`) | `0.875rem` (`14px`) | `600` | `1.375` (`snug`) | `normal` |
| **Bento Card Body** | `--font-sans` | `0.75rem` (`12px`) | `0.75rem` (`12px`) | `400` | `1.625` (`relaxed`) | `normal` |
| **KPI Eyebrow** | `--font-sans` | `0.75rem` (`12px`) | `0.75rem` (`12px`) | `500` | `1.2` | `0.2em` (`uppercase`) |
| **Stat Grid Unit** | `--font-sans` | `11px` | `11px` | `500` | `1.2` | `0.05em` (`uppercase`) |
| **Micro Badge (`NEW`, `8`)** | `--font-sans` | `10px` | `10px` | `600` | `1.0` | `0.025em` (`uppercase`) |

---

### 3. Spacing, Containers, & Radii

Cala feels airy and unhurried because it nests a generous inner container inside outer section margins:

* **Outer Section Frame:**
  * Margin: `8px` (`m-2`) mobile → `16px` (`sm:m-4`) tablet → `32px` (`md:m-8`) desktop.
  * Vertical Padding: `32px` (`py-8`) mobile → `48px` (`md:py-12`) desktop.
  * Scroll Offset: `scroll-mt-12` (`48px`) for anchored navigation.
* **Inner Content Container (`.sub-section`):**
  * Max Width: `72rem` (`1152px` / `max-w-6xl`), centered (`mx-auto`).
  * Horizontal Padding: `16px` (`px-4`) mobile → `64px` (`md:px-16`) desktop.
  * Vertical Padding: `pt-4 pb-12` (`16px` top, `48px` bottom; `md:pb-24` / `96px` on major closing blocks like Pricing).
* **Navigation Container:**
  * Fixed top bar (`bg-beige px-6 py-2`) with inner 3-column grid `[auto_1fr_auto]` capped at `64rem` (`1024px` / `max-w-5xl`).
  * Hand-drawn ink divider underneath capped at `72rem` (`1152px` / `max-w-6xl`).
* **Border Radius Hierarchy (Base `--radius: 0.625rem` / `10px`):**
  * `6px` (`rounded-sm`): Dropdown menu rows.
  * `8px` (`rounded-md`): Dropdown popover, query operator chip (`=`), code copy button.
  * `10px` (`rounded-lg`): Bento taxonomy cards, integration tab buttons, tactile query tokens.
  * `14px` (`rounded-xl`): Primary/secondary CTA buttons, feature vertical tabs, KPI cards, dark code window.
  * `16px` (`rounded-2xl`): `1px`-gap (`gap-px`) stat matrix inside pricing cards.
  * `24px` (`rounded-3xl`): Pricing tier cards (`p-7 md:p-10`) and hero interactive canvas frames.
  * `9999px` (`rounded-full`): Horizontal industry filter tabs, `Explore` pill CTAs, badges, and `8px` status dots.

---

### 4. Signature UI Components & Patterns

#### A. Fixed Editorial Navbar + Hand-Drawn Scroll Rule
* Left: Brand mark + lowercase serif wordmark (`w-24 mix-blend-multiply`).
* Center (`gap-6 text-sm text-brown`): Plain links with animated underline offset (`hover:underline underline-offset-6 hover:underline-offset-4 transition-all`). Count badges use `bg-brown text-beige-50 rounded-full h-4 min-w-4 px-1 text-[10px] font-semibold`.
* Right (`gap-5 text-sm`): External links with `16px` `arrow-up-right` (`Docs ↗`), text `Log in`, and solid espresso `Sign up` (`bg-brown text-white rounded-xl px-4 py-1.5 hover:bg-brown/80`).
* Bottom edge: An organic hand-drawn SVG ink line (`max-w-6xl`) that stays subtle or fades in on scroll rather than a rigid full-bleed `1px solid` CSS border.

#### B. Section Headings with Inline Stippled Illustrations
Major left-aligned `h2` headings (`section-title`) open with a whimsical hand-drawn ink/stippled icon scaled relative to the font size (`h-[1.2em]` to `h-[1.5em] w-auto inline-block`) with `gap-3` (`12px`):
* Examples: A retro robot head for *Agents*, a node constellation for *Structured Knowledge*, a stippled filter funnel for *Endpoints & Industries*, an electric plug for *Integrations*.
* Keep functional UI icons inside tabs and cards strictly as clean **Lucide** strokes (`16px`–`18px`, `stroke-width: 1.75`). Never put cartoon illustrations inside small buttons or bento cards, and never put thin Lucide icons at `60px` next to a Tiempos `h2`.

#### C. Tactile Keycap Query Tokens (Structured Data Proof)
When showing structured paths, schemas, or graph queries (e.g., `Acme . Financials . NetIncomeLoss . From = 2016 . To = 2026`), render each segment as a **tactile 2px hard-offset keycap pill** rather than plain monospace text:
* **Top face:** `bg-blue-100 border border-brown text-blue-700 rounded-lg px-2 py-1 text-sm relative z-10`
* **Hard offset base:** Sibling `span` behind it with `bg-brown absolute inset-x-0 top-0 -bottom-0.5 mt-2 rounded-lg` (creates a crisp solid `#2e2723` bottom lip).
* **Dot connector:** `.` in `text-brown-600 w-2 text-xl text-center`.
* **Inline operator & value:** Operator `=` inside `bg-pink-200 text-pink-600 border border-pink-500/50 rounded-md px-2 py-0.5 mx-2`, followed by value in `text-pink-600`.

#### D. KPI Metric Cards
* 2-column grid (`gap-6 md:gap-8`).
* Surface: `rounded-xl bg-brown/5 p-6 md:p-10` with subtle semantic border (`border border-blue-200/40` or `border-yellow-200/40`, brightening to `60%` on hover).
* Structure:
  1. Eyebrow row (`flex items-center gap-2.5`): `8px` solid circle (`bg-blue` or `bg-yellow`) + `text-xs font-medium uppercase tracking-[0.2em] text-brown`.
  2. Big Tiempos numeral (`mt-4 font-tiempos text-4xl md:text-6xl tabular-nums`) in matching `text-blue` or `text-yellow`.
  3. Grounded 2-line explanation (`mt-4 text-sm md:text-base text-brown leading-relaxed`).

#### E. Split Vertical Tab Rail + Interactive Stage
Used for multi-capability explorations (`#features`) and developer integrations (`#integrate`):
* **Layout:** `flex-col gap-6 md:flex-row md:gap-10`.
* **Left Rail (`role="tablist"`):** Horizontal swipeable strip on mobile (`overflow-x-auto scrollbar-hide`), vertical stack on desktop (`md:flex-col md:gap-1`).
  * Selected tab: Solid `bg-brown` pill (`rounded-xl` or `rounded-lg`), `text-beige-50`, `16px–18px` icon + `text-sm md:text-base font-medium`.
  * Unselected tab: Transparent background, `text-brown-600 hover:text-brown-800`.
* **Right Stage (`flex-1 min-w-0`):**
  * **For Data/Charts:** Cream card (`rounded-xl border border-brown-200/40 bg-beige-50/60 p-5`), top-left italic unit caption (`text-xs italic text-brown-400 mb-4`), clean chart using `#30bfff` stroke (`2px`), solid `#30bfff` circular data nodes (`r="3.5"`), dashed/subtle horizontal gridlines (`stroke: rgba(46,39,35,0.12)`), and muted brown axis labels (`10px–11px`).
  * **For Code/Configs:** Espresso terminal (`rounded-xl bg-brown shadow-lg ring-1 ring-brown-900/20`), header bar (`border-b border-brown-800 px-4 py-3`) with 3 subtle monochrome dots (`h-3 w-3 rounded-full bg-brown-700/60` — **never** red/yellow/green macOS traffic lights!), filename in `text-xs text-brown-400 font-medium`, right `Copy` button (`text-xs text-white hover:bg-brown-800 rounded-md px-2.5 py-1.5`), and `<pre>` in `p-5 md:p-6 text-sm leading-relaxed text-white font-mono`.

#### F. Taxonomy Bento Grid
* 3-column responsive grid (`grid gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4`).
* Card surface: `border border-brown-200 rounded-lg bg-beige-50/60 p-4 lg:p-5`.
* Header (`mb-1.5 flex items-center gap-2.5`): `18px` Lucide icon (`text-brown-700`, `stroke-width: 1.75`) + `h3` (`text-sm font-semibold text-brown leading-snug`).
* Body: Concrete examples and sources in `text-xs leading-relaxed text-brown-600`.

#### G. Dual-Contrast Pricing & Comparison Pair
When contrasting a self-serve/baseline option with an enterprise/flagship option:
* **Baseline Card:** `rounded-3xl bg-beige-200/60 p-7 md:p-10 text-brown`. Includes a `2x2` hairline stat grid (`grid-cols-2 gap-px overflow-hidden rounded-2xl bg-brown/10` with `bg-beige-100 p-4` cells: Tiempos/Sans `text-xl md:text-2xl` value over `11px uppercase tracking-wider text-brown/45` unit). CTA: `bg-brown text-white rounded-xl py-3`.
* **Inverted Flagship Card:** `rounded-3xl bg-brown p-7 md:p-10 text-beige-50`. Muted copy in `text-beige-50/60`, divider rule `h-px bg-beige-50/15`, checkmarks in `text-beige-50/50`. CTA: `bg-beige-50 text-brown hover:bg-white rounded-xl py-3`.

#### H. Border-Divided Editorial Accordion (FAQs)
* Never wrap FAQ items in individual cards. Use a single vertical stack with `border-b border-b-brown last:border-b-0`.
* Trigger (`py-4 flex justify-between items-start gap-4`): Question in `font-tiempos text-xl md:text-3xl text-brown`, `16px` chevron in `text-brown-500` rotating `180deg` when open.

---

## Hand-Drawn SVG & Illustration System ("The Cala Soul")

Cala's HTML relies on organic ink SVGs and multiply-blended drawings to prevent its structured data grids from feeling sterile. Whenever you build a Cala page, **author inline SVGs** for these signature touches (see [references/svg-ink-and-motifs.md](./references/svg-ink-and-motifs.md) for copy-paste SVG paths):

1. **Hand-Drawn Ink Dividers:** Use slightly irregular, tapered horizontal SVG paths (`stroke="#2e2723"`) beneath the navbar and above the footer instead of generic `<hr>` tags.
2. **Rhetorical Strikethroughs:** When contrasting legacy pain with Cala's approach (e.g., *"Cala is ~~clutter~~ clarity"*, *"~~scraping~~ querying"*), cross out the rejected word using an expressive multi-pass SVG ink scribble (`stroke="#2e2723"`, `opacity="0.88"`) overlaid at `top-1/2 left-1/2 -translate-x-1/2`. Vary scribble paths across sibling lines so no two look mechanically identical.
3. **Wavy & Tilted Manifesto Underlines:** Emphasize key human conclusions (*"Now the data is too."*) with a bold hand-drawn wavy squiggle or `-1deg` tilted brush stroke underneath.
4. **Multiply Blending on Raster/Sketch Art:** Any illustration with an off-white paper ground must use `mix-blend-mode: multiply` (`mix-blend-multiply`) so its background disappears seamlessly into `#f6e8cd`.

---

## Anti-Patterns to Reject

Never ship any of these generic AI/SaaS design reflexes on a Cala surface:

* **No stark white `#ffffff` or dark-mode `#09090b` page backgrounds.** Cala's identity lives on warm `#f6e8cd` parchment with `#2e2723` espresso contrast blocks.
* **No bold serif headings.** Setting Tiempos / Instrument Serif at `font-weight: 700` destroys its editorial delicacy; keep display serifs at `400`.
* **No neon gradients, purple-to-blue AI glows, glassmorphic dark cards, or blurred aurora blobs.**
* **No red/yellow/green macOS traffic-light dots** on code blocks—always use monochrome `bg-brown-700/60` dots on `#2e2723`.
* **No heavy drop shadows on parchment cards.** Bento and chart cards use `1px` `border-brown-200` hairlines and translucent `bg-beige-50/60` fills, reserving shadows (`shadow-lg`) only for floating popovers and dark espresso code windows.
* **No generic stock photos or 3D glossy renders.** Use structured live data, tactile query tokens, clean sky-blue charts, or stippled black-ink line art.
* **No white text on `#ffc234` yellow buttons.** Always pair `#ffc234` with `#2e2723` ink for crisp WCAG contrast and authentic brand feel.

---

## Pre-Handoff Verification Pass

Before completing any CALA.AI design or frontend implementation, privately verify:

1. **Squint & Palette Check:** Is `#f6e8cd` the unmistakable canvas, `#2e2723` the primary anchor ink, and `#fcf8f099` used for light cards? Are `#ffc234` and `#30bfff` used as deliberate focal accents rather than splashed everywhere?
2. **Typographic Contrast:** Do all `h1`/`h2`/KPI numerals/FAQ questions use regular-weight editorial serif (`Tiempos` / `Instrument Serif` at `400`) while subtitles, tabs, buttons, and bento cards use crisp grotesque sans (`Waldenburg` / `Plus Jakarta Sans`)?
3. **Tactile & Hand-Drawn Craft:** Does the page include organic SVG ink touches (navbar/footer ink rule, a scribble strikethrough or wavy underline on narrative claims, or an `1.2em` stippled heading icon) so it feels genuinely Cala rather than a recolored template?
4. **Responsive Reflow:** Do outer `m-2 sm:m-4 md:m-8` frames, `.sub-section` (`px-4 md:px-16`), horizontal-to-vertical tab rails, and query pill wrapping (`flex-wrap`) work cleanly from `375px` mobile to `1440px` desktop without horizontal overflow?
