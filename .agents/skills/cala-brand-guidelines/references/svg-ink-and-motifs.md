# CALA.AI Hand-Drawn SVG Ink & Illustration System

Cala's distinct personality comes from pairing structured, developer-grade UI with **tactile, hand-sketched black-brown ink (`#2e2723`)**. Without these organic SVG layers, a Cala page risks looking like a plain beige SaaS site; with them, it feels like an illustrated editorial journal for AI engineers.

---

## Core Authoring Rules for Cala SVGs

1. **Ink Color:** Always draw with `#2e2723` (`var(--cala-brown)`) or `currentColor` inside `.text-brown` containers—never pure `#000000`.
2. **Organic Imperfection:** Avoid mathematically rigid straight `<line>` elements for editorial rules, strikethroughs, and underlines. Use `<path>` curves (`C` / `Q`) with slight vertical wobble (`±1.5px`), subtle taper or multi-pass strokes, and `stroke-linecap="round"` + `stroke-linejoin="round"`.
3. **Two Strict Icon Registers (Never Mix Them):**
   * **Editorial Heading Companions (`1.2em` – `1.5em`):** Placed immediately left of `h2.cala-section-title`. Hand-drawn, whimsical, slightly asymmetrical ink drawings with fine stipple dots (`<circle r="0.9">` clusters) and expressive character (e.g., retro robot with heart eyes, stippled funnel filtering symbols, constellation node graph).
   * **Functional UI Controls (`16px` – `18px`):** Placed inside dropdowns, pill tabs, vertical tabs, bento cards, and buttons. Clean geometric **Lucide** icons (`stroke-width="1.75"` or `"2"`).
4. **Seamless Paper Blending:** Whenever embedding rasterized sketches or shaded SVG artwork with off-white fills, apply `mix-blend-mode: multiply` (`class="mix-blend-multiply"`) so light backgrounds melt into `#f6e8cd`.

---

## 1. Hand-Drawn Horizontal Section & Navbar Rules

Used beneath the sticky navigation bar (`max-w-6xl`) and above the footer (`max-w-6xl`) instead of sterile `1px solid` CSS borders.

```html
<!-- Hand-drawn organic charcoal rule (Navbar / Footer divider) -->
<svg viewBox="0 0 1152 8" fill="none" xmlns="http://www.w3.org/2000/svg"
     class="w-full h-auto max-h-2 text-brown" aria-hidden="true" preserveAspectRatio="none">
  <path d="M2 4.6C185 3.1 392 5.4 584 3.8C776 2.3 968 4.9 1150 3.5"
        stroke="#2e2723" stroke-width="1.65" stroke-linecap="round"/>
  <path d="M14 5.1C240 4.2 510 3.4 820 4.6C960 5.1 1080 3.9 1146 4.2"
        stroke="#2e2723" stroke-width="0.75" stroke-opacity="0.45" stroke-linecap="round"/>
</svg>
```

---

## 2. Expressive Rhetorical Strikethrough Scribbles

Used in contrast litanies (e.g., `Cala is ~~clutter~~ clarity`, `Cala is ~~search~~ infrastructure`).
**Rule:** When stacking multiple crossed-out lines, **alternate between different scribble geometries** so each rejected word feels crossed out by hand in real time.

### Variant A: Dense Multi-Pass Marker Scrawl (e.g., *clutter*, *answers*, *scattered*)
```html
<span class="relative inline-block">
  clutter
  <svg viewBox="0 0 180 32" fill="none" xmlns="http://www.w3.org/2000/svg"
       class="pointer-events-none absolute left-1/2 top-1/2 w-[108%] -translate-x-1/2 -translate-y-[38%]"
       aria-hidden="true">
    <path d="M4 17C52 13 124 14 176 15.5M8 21.5C64 18.5 118 19.5 172 18M12 13.5C70 15 130 12 169 14"
          stroke="#2e2723" stroke-width="3.4" stroke-linecap="round" stroke-opacity="0.88"/>
  </svg>
</span>
```

### Variant B: Crisp Double-Line Editorial Crossout (e.g., *search*)
```html
<span class="relative inline-block">
  search
  <svg viewBox="0 0 180 28" fill="none" xmlns="http://www.w3.org/2000/svg"
       class="pointer-events-none absolute left-1/2 top-1/2 w-[106%] -translate-x-1/2 -translate-y-[40%]"
       aria-hidden="true">
    <path d="M3 13.5C60 12.2 122 13.8 177 12.6M6 17.8C66 16.9 125 17.5 174 16.8"
          stroke="#2e2723" stroke-width="2.2" stroke-linecap="round"/>
  </svg>
</span>
```

### Variant C: Energetic Zig-Zag / Diagonal Scratch (e.g., *static*, *hype*, *drift*)
```html
<span class="relative inline-block">
  hype
  <svg viewBox="0 0 150 36" fill="none" xmlns="http://www.w3.org/2000/svg"
       class="pointer-events-none absolute left-1/2 top-1/2 w-[110%] -translate-x-1/2 -translate-y-[42%]"
       aria-hidden="true">
    <path d="M8 22L36 10L24 25L62 9L50 26L90 10L78 25L118 11L108 24L142 13"
          stroke="#2e2723" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.85"/>
    <path d="M4 18C48 16.5 98 18.5 146 17"
          stroke="#2e2723" stroke-width="2.4" stroke-linecap="round"/>
  </svg>
</span>
```

---

## 3. Manifesto Underlines (Tilted Brush & Wavy Squiggle)

Used beneath hand-lettered `Stefan-Simple` callouts or closing Tiempos punchlines (*"Now the data is too."*).

### Tilted Hand-Drawn Underline (`-rotate-1`)
```html
<span class="cala-hand relative inline-block ml-2">
  out of reach.
  <svg viewBox="0 0 220 10" fill="none" xmlns="http://www.w3.org/2000/svg"
       class="absolute left-0 -bottom-1.5 w-full h-2 -rotate-1" aria-hidden="true" preserveAspectRatio="none">
    <path d="M2 6.5C72 3.8 148 5.2 218 4.1" stroke="#2e2723" stroke-width="3.2" stroke-linecap="round"/>
  </svg>
</span>
```

### Bold Wavy Ink Squiggle (`Now the data is too.`)
```html
<span class="relative inline-block">
  data is too.
  <svg viewBox="0 0 240 20" fill="none" xmlns="http://www.w3.org/2000/svg"
       class="absolute left-0 -bottom-3 w-full h-4" aria-hidden="true" preserveAspectRatio="none">
    <path d="M4 11C16 4 28 17 40 10C52 3 64 17 76 10C88 3 100 17 112 10C124 3 136 17 148 10C160 3 172 17 184 10C196 3 208 16 220 10C227 6.5 233 11 237 9.5"
          stroke="#2e2723" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</span>
```

---

## 4. Inline Heading Companion Illustrations (`1.2em` – `1.5em`)

Place immediately inside `h2.cala-section-title` with `class="cala-section-title-icon"` (`height: 1.2em; width: auto`). Below are four canonical Cala inline ink icons ready to embed or adapt:

### A. Retro Agent Robot (Metrics / AI Agents)
```html
<svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg" class="cala-section-title-icon" aria-hidden="true">
  <!-- Antenna -->
  <path d="M28 15V7M28 7C25.5 7 24 5.5 24 4C24 2.5 25.8 1.5 28 1.5C30.2 1.5 32 2.5 32 4C32 5.5 30.5 7 28 7Z" stroke="#2e2723" stroke-width="2" stroke-linecap="round"/>
  <!-- Head Box (organic hand-drawn rect) -->
  <path d="M12 18C12 15.8 14 15 28 15C42 15 44 15.8 44 18C44.5 26 44.2 35 43.8 43C43.5 45.5 41 46.5 28 46.5C15 46.5 12.5 45.5 12.2 43C11.8 35 11.5 26 12 18Z" fill="#fcf8f0" stroke="#2e2723" stroke-width="2.1" stroke-linejoin="round"/>
  <!-- Ears -->
  <path d="M11.8 25H8.5C7.2 25 7 26.5 7 30C7 33.5 7.2 35 8.5 35H11.8M44.2 25H47.5C48.8 25 49 26.5 49 30C49 33.5 48.8 35 47.5 35H44.2" stroke="#2e2723" stroke-width="2" stroke-linecap="round"/>
  <!-- Heart Eyes -->
  <path d="M20.5 27.5C19 25.2 16 25.8 16.5 28.5C16.8 30.2 20.5 32.5 20.5 32.5C20.5 32.5 24.2 30.2 24.5 28.5C25 25.8 22 25.2 20.5 27.5Z" stroke="#2e2723" stroke-width="1.7" stroke-linejoin="round"/>
  <path d="M35.5 27.5C34 25.2 31 25.8 31.5 28.5C31.8 30.2 35.5 32.5 35.5 32.5C35.5 32.5 39.2 30.2 39.5 28.5C40 25.8 37 25.2 35.5 27.5Z" stroke="#2e2723" stroke-width="1.7" stroke-linejoin="round"/>
  <!-- Toothy Grin -->
  <path d="M19 37.5C23 40.5 33 40.5 37 37.5C36.5 41.8 33 43.2 28 43.2C23 43.2 19.5 41.8 19 37.5Z" stroke="#2e2723" stroke-width="1.7" stroke-linejoin="round"/>
  <path d="M24 38.8V42.6M28 39.3V43.1M32 38.8V42.6" stroke="#2e2723" stroke-width="1.3"/>
  <!-- Stipple Shading -->
  <circle cx="15" cy="43" r="0.9" fill="#2e2723"/><circle cx="17.5" cy="44" r="0.9" fill="#2e2723"/><circle cx="40.5" cy="43.5" r="0.9" fill="#2e2723"/>
</svg>
```

### B. Knowledge Graph Constellation (Structured Knowledge / Features)
```html
<svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg" class="cala-section-title-icon" aria-hidden="true">
  <path d="M11 14L25 27M25 27L41 12M25 27L16 45M25 27L44 37M41 12L46 23" stroke="#2e2723" stroke-width="2" stroke-linecap="round"/>
  <circle cx="10" cy="13" r="3.2" fill="#fcf8f0" stroke="#2e2723" stroke-width="2"/>
  <circle cx="25" cy="27" r="4" fill="#fcf8f0" stroke="#2e2723" stroke-width="2.1"/>
  <circle cx="41" cy="12" r="3.2" fill="#fcf8f0" stroke="#2e2723" stroke-width="2"/>
  <circle cx="46.5" cy="23.5" r="2.6" fill="#2e2723"/>
  <circle cx="15.5" cy="45.5" r="3.2" fill="#fcf8f0" stroke="#2e2723" stroke-width="2"/>
  <circle cx="44.5" cy="37.5" r="3.2" fill="#fcf8f0" stroke="#2e2723" stroke-width="2"/>
</svg>
```

### C. Stippled Data Funnel (Endpoints / Verticals)
```html
<svg viewBox="0 0 56 64" fill="none" xmlns="http://www.w3.org/2000/svg" class="cala-section-title-icon" style="height: 1.45em" aria-hidden="true">
  <!-- Floating raw input symbols -->
  <path d="M15 9L18 13M18 9L15 13M27 7C29 7 30 9 28 11C26 13 29 14 31 13M39 8.5L42 12.5L37 13Z" stroke="#2e2723" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Funnel Rim & Body -->
  <ellipse cx="28" cy="21" rx="18" ry="4.5" fill="#fcf8f0" stroke="#2e2723" stroke-width="2"/>
  <path d="M10 21L24.5 40.5V53.5L31.5 50.5V40.5L46 21" stroke="#2e2723" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Stipple texture -->
  <circle cx="21" cy="29" r="0.9" fill="#2e2723"/><circle cx="24" cy="32" r="0.9" fill="#2e2723"/><circle cx="26.5" cy="36" r="0.9" fill="#2e2723"/>
  <circle cx="28" cy="58" r="1.4" fill="#2e2723"/><circle cx="28" cy="62" r="1.1" fill="#2e2723"/>
</svg>
```

### D. Hand-Drawn Connector Plug (Integrations / MCP)
```html
<svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg" class="cala-section-title-icon" aria-hidden="true">
  <path d="M21 10V20M35 10V20" stroke="#2e2723" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M15 20H41V30C41 37.2 35.2 42 28 42C20.8 42 15 37.2 15 30V20Z" fill="#fcf8f0" stroke="#2e2723" stroke-width="2.1" stroke-linejoin="round"/>
  <path d="M28 42V49C28 52 32 53 36 51" stroke="#2e2723" stroke-width="2.1" stroke-linecap="round"/>
  <circle cx="22" cy="27" r="1" fill="#2e2723"/><circle cx="25" cy="34" r="1" fill="#2e2723"/><circle cx="34" cy="31" r="1" fill="#2e2723"/>
</svg>
```

---

## 5. Brand Wordmark Lockup (Shell Emblem + Lowercase Serif)

When the official raster logo asset is unavailable in standalone prototypes, use this clean vector approximation (`color: #2e2723`):

```html
<a href="/" aria-label="Cala Home" style="display:inline-flex;align-items:center;gap:0.45rem;color:#2e2723;text-decoration:none;">
  <svg width="24" height="24" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M19.5 5.2C14.2 3.4 8.2 6.4 6.6 11.9C5.0 17.4 8.2 22.9 13.8 24.1C16.4 24.7 19.1 24.0 21.1 22.4C17.2 22.9 13.3 20.4 12.4 16.3C11.4 11.8 14.4 7.3 19.5 5.2Z" fill="#2e2723"/>
    <path d="M22.2 8.4C18.4 7.8 14.9 10.5 14.5 14.3C14.1 18.0 16.9 21.1 20.7 21.2" stroke="#2e2723" stroke-width="2.1" stroke-linecap="round"/>
  </svg>
  <span style="font-family:var(--cala-font-serif);font-size:1.65rem;font-weight:400;letter-spacing:-0.03em;line-height:1;">cala</span>
</a>
```

---

## 6. Data Chart SVG Styling Rules

When rendering inline SVG or Recharts visualizations inside `.cala-chart-card`:
* **Container:** `rgba(252, 248, 240, 0.6)` (`bg-beige-50/60`), `1px solid rgba(216, 201, 193, 0.45)`, `border-radius: 14px`, `padding: 20px`.
* **Caption:** Top-left italic label (`Net Income / Loss ($B)`) in `12px` `--cala-brown-400`.
* **Gridlines:** Horizontal only, `stroke="rgba(46, 39, 35, 0.08)"`, `stroke-width="1"`. Omit vertical gridlines and outer chart box borders.
* **Primary Series:** Smooth monotone cubic bezier path in `--cala-blue` (`#30bfff`), `stroke-width="2"`, `fill="none"`.
* **Data Points:** Solid circles `fill="#30bfff"`, `r="3.5"`, no white stroke halo.
* **Axes:** Tick text in `--cala-brown-500`, `font-size="10px"`, sans-serif. X-axis temporal labels rotated `-45deg` when dense (`Jun 2016` … `Sep 2025`).
