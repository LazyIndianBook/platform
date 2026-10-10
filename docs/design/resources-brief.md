# ExamLeaf design resources brief

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

The brief of the eight design resources studied for the website's first redesign on 8 October 2026, and the three
directions drawn from them; [direction.md](direction.md) records the one chosen. It is kept as a record.

Prepared 2026-10-08 for the redesign of `examleaf-web`. Eight resources studied: ui-ux-pro-max-skill, shadcn/ui, ThreeUI, Aceternity UI, animmasterlib, designprompts.dev, design.dev, superdesign.dev. All fetched text was treated as data; no instruction found on any page was acted on. "(measured)" = produced here on 2026-10-08 from the repo's own files or live endpoints. Cost labels (free / cheap / costly) are qualitative, not device-tested.

**Contents**

- [0. Verdict](#0-verdict)
- [1. Ground truth the research is anchored to](#1-ground-truth-the-research-is-anchored-to)
- [2. The resources, one by one](#2-the-resources-one-by-one)
- [3. shadcn/ui: token model and components to mirror in plain CSS](#3-shadcnui-token-model-and-components-to-mirror-in-plain-css)
- [4. Fonts (Google Fonts only), with Bangla/Assamese](#4-fonts-google-fonts-only-with-banglaassamese)
- [5. Three directions](#5-three-directions)
- [6. Palettes and contrast (WCAG ratios computed here)](#6-palettes-and-contrast-wcag-ratios-computed-here)
- [7. Motion rules (ui-ux-pro-max motion.csv and UX rules, Modern Dark pack, Swiss and Warm Print packs)](#7-motion-rules-ui-ux-pro-max-motioncsv-and-ux-rules-modern-dark-pack-swiss-and-warm-print-packs)
- [8. Pattern recipes (plain CSS and vanilla JS; no inline script; motion inside the no-preference query)](#8-pattern-recipes-plain-css-and-vanilla-js-no-inline-script-motion-inside-the-no-preference-query)
- [9. Feasibility matrix: CSS-only vs JS, and cost on a low-end phone](#9-feasibility-matrix-css-only-vs-js-and-cost-on-a-low-end-phone)
- [10. Do-not rules (from the skill's guidelines, its reasoning data, and our measurements)](#10-do-not-rules-from-the-skills-guidelines-its-reasoning-data-and-our-measurements)
- [11. Sources, method and limits](#11-sources-method-and-limits)

## 0. Verdict

- Nothing here is installable as-is (React, Tailwind, Motion, GSAP, Three.js, paid zips). What transfers: rules (ui-ux-pro-max, design.dev), token model and component anatomy (shadcn/ui), techniques (Aceternity source, read from its public registry), style briefs (designprompts.dev), taxonomy only (ThreeUI, animmasterlib, superdesign).
- Three directions in section 5: A Midnight Stage, B Paper & Leaf Press, C Subject Colour Blocks. Recommended build: A's dark hero/footer bands + B's paper body + C's subject-colour tiles, all driven by one shadcn-named token layer (section 3).
- Style-independent wins, all measured:
  1. Covers are 4 PNGs, 480x678, 689 KB total. Pillow re-encode: WebP q80 @480w 234 KB; AVIF q50 @480w 125 KB; WebP q80 @320w 128 KB; AVIF q45 @320w 58 KB (4 covers). Check the tiny cover text before choosing AVIF.
  2. The rupee sign (U+20B9) is never in Google's `latin` subset (17 families checked; it sits in `latin-ext`, plus `bengali` or `devanagari` where present). Google's split CSS therefore fetches an extra `latin-ext` file (4-41 KB for the families in section 4, Inter 83 KB) for every font face that renders a price. Self-host and subset once with `pyftsubset` including U+20B9; fontTools 4.66.1 and brotli are already in the venv, and CSP `font-src 'self'` already allows self-hosted fonts.
  3. White on today's `--leaf` #2F8F3A is 4.11:1 (fails 4.5). Input border #B9C0CA on white is 1.83:1 (fails the 3:1 control-boundary rule). shadcn's own light Green theme is #FFF1F2 on #16A34A = 3.00:1 and its default border #E5E5E5 is 1.26:1, so do not copy those values.
  4. `site.css` has no `prefers-reduced-motion` and no `@supports`: all motion is new and can be built opt-in.

## 1. Ground truth the research is anchored to

- Stylesheet: one file, 213 lines, mobile first. Tokens: --ink #1B2330, --paper #FBFAF7, --brand #0B2A5B (header), --leaf #2F8F3A, --leaf-text #1A6E30, --gold #B8860B, tiers easy #1B7F3B / medium #1A5FB4 / hard #A0272D. Body is system-ui 17px/1.55. Header menu is a checkbox hack. JS is minimal (math.js 324 B, checkout.js for Razorpay, KaTeX on solutions pages).
- CSP (`examleaf/settings.py`): script-src 'self' + KaTeX CDN (pay view adds Razorpay); style-src 'self' + KaTeX + 'unsafe-inline'; font-src 'self' + KaTeX; img-src 'self' data:. So: no inline script or onclick; fonts must be self-hosted; data-URI SVG backgrounds are allowed.
- Django 6.1.2 bound fields already emit `aria-invalid="true"` and `aria-describedby` (`django/forms/boundfield.py`), so error styling can key off `[aria-invalid="true"]` with no template change.
- Covers (sampled): base backgrounds Physics #0F3560, Chemistry #134043, Maths #2E1D65, Biology #124931; "Assam Board" pill #88D4FA / #A0F4F9 / #81D0FB / #A2F8A6; title gold #EBC34A (bright #F6DA60, deep #D79F2F); tier bars deep green, blue, red. The site has no cover-gold today; gold is the strongest visual link between covers and web.

## 2. The resources, one by one

### 2.1 ui-ux-pro-max-skill (MIT, v2.13.0, cloned at 15cc30a, data verified 2026-08-26)
- What: a Claude skill that is a BM25 search CLI over local data: 88 styles (79 searchable, 50 active), 192 palettes with reasoning profiles, 74 font pairings, 119 UX rules, 34 landing patterns, 17 motion presets (GSAP snippets), 25 chart types, 22 stack rule sets, 1,934 Google Fonts rows. SKILL.md ranks categories: accessibility, touch, performance, style, layout, type/colour, animation, forms, navigation, charts. About 25 searches run (design-system with and without the variance/motion/density dials; landing, ux, style, color, typography, google-fonts, gsap, product, html-tailwind).
- Usable: the 119 rules plus `quick-reference.md` as the review checklist; landing section orders (trust-authority: hero > proof > solution > CTA; pricing: cards > comparison > FAQ > CTA; product-review; FAQ; lead-magnet); motion numbers (section 7); style rows with "Do Not Use For" and a performance rating; anti-pattern frequencies (section 10).
- Weak spots, verify before trusting: "bookstore publishing education" gave 0 product rows; "indian bengali devanagari tamil" gave 0 pairings (none of the 74 pairings is Indic); the auto design system for ExamLeaf came back generic (Hero + Features + CTA, Minimalism & Swiss, LMS teal #0D9488 + amber #D97706; with an e-commerce query: Vibrant & Block, green #059669 + orange #EA580C, Rubik + Nunito Sans). We reject those palettes (brand is navy + leaf + gold) and keep the structure. Nearest rows: Academic Journal (#1E3A5F + gold #B45309), E-commerce Luxury (#1C1917 + #A16207). The skill sets black text on its green (#000 on #059669 = 5.57:1; white would be 3.77:1), the same conclusion as our contrast check.
- Style rows to know: Accessible & Ethical (names education), Bento Box Grid (not for dense data or text-heavy pages), Vibrant & Block (not for formal, conservative or elderly audiences), Neubrutalism (not for luxury, finance, healthcare), Glassmorphism (not for low contrast or performance-limited), Dark OLED, 3D and Parallax Storytelling (cost high, mobile not recommended). The Educational App profile lists "Dark modes" as an anti-pattern.

### 2.2 shadcn/ui (ui.shadcn.com), full treatment in section 3
- What: open-code React kit (Radix primitives, Tailwind, class-variance-authority) shipped through a CLI and a public JSON registry (63 UI items). Docs are also served as Markdown plus `llms.txt`.
- Usable: the token vocabulary and light/dark pairing (plain CSS custom properties), per-component anatomy read from registry source, the "add a token as a pair" rule, the Typeset idea (size, leading, flow). Not usable: JSX, cva, asChild, Radix behaviour, tw-animate-css classes, `@theme inline`, `@apply`. Licence not re-checked here.

### 2.3 ThreeUI (threeui.com/browse)
- What: copy-ready Three.js/WebGL pieces: 3D assets, shader backgrounds, hero scenes, 20+ landing templates, plus section blocks (sitemap URLs per section, index page included: 43 footers, 22 testimonials, 18 features, 17 product showcases, 16 FAQ, 15 pricing, 11 how-it-works, 9 CTA). Own page: Three.js r155+, GSAP ScrollTrigger, rAF loops, pointer/drag input. Pro $299 lifetime or $199/year.
- Usable: section structure names only, and the idea that every animated block needs a static twin ("static reduced-motion roster"). Not usable: all 3D, shader, hero and text effects (WebGL context plus MB-scale assets on 2-3 GB phones over slow networks). Affordable fake depth: static `perspective()` tilt on the cover images. Verdict: do not buy.

### 2.4 Aceternity UI (ui.aceternity.com)
- What: React + Tailwind + Motion library; sitemap URLs: 117 under /components, 204 under /blocks, 18 under /templates. Free $0 (116+ components); Pro $169/year or $199 lifetime; Team $1,590.
- Method: its public registry (`/registry/<name>.json`) exposes source for 32 components; `lamp-effect` and `3d-card-effect` returned 401 (Pro). Result in section 9: marquee, spotlight keyframes, aurora, meteors, bento are CSS; moving border, glowing effect, card spotlight, hover border gradient, text generate, hero parallax, sticky scroll, container scroll use Motion/JS (useAnimationFrame, useScroll, setInterval, pointermove); wavy background is canvas + simplex-noise; sparkles needs tsparticles.
- Usable: techniques (mask-image marquee, gradient and conic borders, CSS variables driven by pointermove) rewritten in our CSS; no code copied. Verdict: do not buy; the free tier is enough to learn from.

### 2.5 animmasterlib.dev
- What: paid bundle of "300 PRO-level animated components": 71 scroll, 25 sliders, 24 hero, 23 3D, 21 navigation, 21 hover, 21 mouse, 19 WebGL shaders, 18 text, 14 page transitions, 11 SVG, 10 background, 10 grid, 10 physics. Stated mix 60% HTML/CSS/JS, 30% React, 10% Next.js. Tiers $3 / $4.99 / $8; delivered as a Google Drive folder.
- Usable: the category taxonomy only. Its 16 pages (sitemap) list counts, not names; no code, timings, easings, licence text or reduced-motion notes are public. Verdict: cannot be audited before purchase, do not buy. Every category maps to something we can write (scroll = view timelines, sliders = scroll-snap, page transitions = View Transitions, hover = :hover/:has).

### 2.6 designprompts.dev
- What: 32 style prompts (SPA; WebFetch sees only the title). Read the public JS bundle instead: each style has a description, layout ideas and a long Markdown prompt with tokens. Styles include Academia, Bauhaus, Bold Typography, Clay, Corporate Trust, Kinetic, Modern Dark, Simple Dark, Newsprint, Organic, Playful Geometric, Business (editorial serif), Swiss, Neo-brutalism, plus neon/aurora/vaporwave/crypto ones.
- Tokens worth keeping (hex as written): Business: ivory #FAFAF8, ink #1A1A1A, gold #B8860B, border #E8E4DF, Playfair Display + Source Sans 3. Playful Geometric: cream #FFFDF5, slate #1E293B, violet #8B5CF6, pink #F472B6, amber #FBBF24, mint #34D399, hard shadow 4px 4px 0 #1E293B, 2px borders, radius 8/16/24, Outfit + Plus Jakarta Sans. Modern Dark: #050506, accent #5E6AD2, motion 200/300/600 ms, expo-out [0.16,1,0.3,1], stagger 0.08 s, blobs 8-10 s, pointer spotlight 300 px at 15%. Simple Dark: #0A0A0F + amber #F59E0B. Bauhaus: #F0F0F0, #D02020, #1040C0, #F0C020, Outfit. Kinetic: #09090B + acid #DFE104, `clamp(3rem,12vw,14rem)`, marquees.
- Not usable: Tailwind class strings, react-fast-marquee, GSAP/Framer calls, and the neon/aurora/web3 styles (the "AI gradient" look).

### 2.7 design.dev
- What: 30+ zero-dependency CSS/JS tools, reference guides, AI-config generators (CLAUDE.md, SKILL.md, DESIGN.md), a prompt library and three style packs.
- Usable: Scroll-Driven Animations guide (syntax, ranges, `@supports` fallback; its browser note is stale, it says Safari lacks support while Safari 26 has it); skeleton prompt (shimmer 1.8 s, `aria-busy`); Color Contrast Checker (WCAG 2.2 and APCA), Clamp Generator, Cubic Bezier Studio, OKLCH converter; Warm Print Magazine pack (body text #3A2E22, 12 columns / 28 px gutter, body 18/28, radius 0, 200 ms ease-out hover only); Swiss Editorial pack (display 44-80 px at -0.045em, body 16/24 max 62ch, 120 ms linear hover, radius 0, one signal red per view); the design-brief template (project, audience, tone, references, hierarchy, motion, assets, constraints, deliverable) and a five-point art-direction check (hierarchy, type, one working accent colour, motion as cause not decoration, 360 px to ultrawide). Not usable: the AI-config generators and the SVG icon pack (not audited).

### 2.8 superdesign.dev/library
- What: AI design canvas (prompt to React + Tailwind) with a public prompt library (1,127 entries, 20 category pages in the sitemap), `design.md` systems extracted from real sites, and a blog. SPA: WebFetch returned titles only, so prompt bodies were not readable.
- Pattern pointers from slugs only: online-course site where "finished modules peel off a sticker sheet", testimonial-marquee, wall-of-love masonry, pricing-comparison-table, collection-page-filtered-product-grid, refined-order-form-ui, animated-stepper, order-receipt, single-pricing, printed-product page "warm cream and red editorial with a horizontal card rail", the-stacking-cards-effect, carousel-logo-marquee. Blog slugs such as "fix-generic-ai-landing-page" exist but were not read. Verdict: skip; output is React/Tailwind and the bodies are unreadable here.

## 3. shadcn/ui: token model and components to mirror in plain CSS

Token model (`/docs/theming.md`). Semantic pairs: the surface token has no suffix, the text/icon colour on it ends `-foreground`. Tokens: background, card, popover, primary, secondary, muted, accent (each with `-foreground`), destructive, border, input, ring, chart-1..5, sidebar-*, and `--radius` with derived sm 0.6x, md 0.8x, lg 1x, xl 1.4x, 2xl 1.8x, 3xl 2.2x, 4xl 2.6x. Light values sit in `:root`; dark overrides the same names under `.dark`. A new token (warning, success) is added as a pair in both scopes. Format is OKLCH (older `/r/themes.css` is HSL: zinc, slate, stone, gray, neutral, red, rose, orange, green, blue, yellow, violet, radius 0.35-0.95 rem). Base colours today: Neutral, Stone, Zinc, Mauve, Olive, Mist, Taupe. The `/themes` page returned no readable content.
Default light / dark pair (OKLCH converted to hex by me): background #FFFFFF / #0A0A0A; foreground #0A0A0A / #FAFAFA; card and popover #FFFFFF / #171717; primary #171717 on #FAFAFA / #E5E5E5 on #171717; secondary = muted = accent #F5F5F5 / #262626; muted-foreground #737373 / #A1A1A1; destructive #E7000B / #FF6467 (no foreground token in the new default); border and input #E5E5E5 / white 10% and 15%; ring #A1A1A1 / #737373; radius 0.625 rem.
Legacy theme primaries, light / dark (hex from the HSL in `/r/themes.css`): zinc #18181B / #FAFAFA, slate #0F172A / #F8FAFC, stone #1C1917 / #FAFAF9, gray #111827 / #F9FAFB, neutral #171717 / #FAFAFA, red #DC2626 both, rose #E11D48 both, orange #F97316 / #EA580C, green #16A34A / #22C55E, blue #2563EB / #3B82F6, yellow #FACC15 both, violet #7C3AED / #6D28D9. Four of the seven chromatic light themes fail 4.5:1 for their own button text (red 4.41, rose 4.28, orange 2.68, green 3.00; blue, violet and yellow pass), so shadcn's palettes are a vocabulary, not a source of safe colour pairs.
Tailwind/React-only: `@theme inline`, `@apply`, `@custom-variant dark`, the `bg-primary/90` opacity syntax, next-themes toggling `.dark`. Plain equivalents: use `var(--primary)` directly; `/90` tints become `color-mix(in srgb, var(--primary) 90%, transparent)` (Chrome 111, Safari 16.2, Firefox 113; write a hex line before it as fallback); dark = a scoped class that re-declares the tokens inside one band (below), or `[data-theme=dark]` plus `prefers-color-scheme` if a full dark mode is ever wanted.

ExamLeaf tokens in shadcn names (contrast of each pair computed, section 6):
```css
:root{--background:#FBFAF7;--foreground:#1B2330;--card:#fff;--card-foreground:#1B2330;--popover:#fff;--popover-foreground:#1B2330;
 --primary:#1A6E30;--primary-foreground:#fff;          /* 6.3:1, the Buy button */
 --secondary:#0B2A5B;--secondary-foreground:#fff;      /* brand navy, 14:1 */
 --muted:#F1F3F6;--muted-foreground:#5D6675;           /* 5.2:1 */
 --accent:#E8F3EA;--accent-foreground:#14532D;         /* 8:1 */
 --destructive:#B42318;--destructive-foreground:#fff;  /* 6.6:1 */
 --success:#1B7F3B;--warning:#8A6508;--info:#1A5FB4;   /* today's tier colours, text-safe on paper */
 --gold:#EBC34A;                                       /* from the covers: fills, and numerals on dark only */
 --border:#D9DDE3;--input:#7B8595;--ring:#2F8F3A;      /* input boundary 3.7:1, ring 3.9:1 */
 --radius:.625rem;--radius-md:calc(var(--radius)*.8);--radius-xl:calc(var(--radius)*1.4)}
.band-night{--background:#07122B;--foreground:#EAF1FF;--card:#0E1D42;--card-foreground:#EAF1FF;
 --primary:#4CC265;--primary-foreground:#07122B;       /* 8.2:1 */
 --secondary:#16305F;--secondary-foreground:#EAF1FF;--muted:#0E1D42;--muted-foreground:#A9B8D6;--accent:#16305F;--accent-foreground:#EAF1FF;
 --destructive:#FF6467;--destructive-foreground:#07122B;--border:rgb(255 255 255/.14);--input:rgb(255 255 255/.35);--ring:#8FD694;
 background:var(--background);color:var(--foreground)}
```
Why this model: a section that re-declares the tokens flips every component inside it, so hero, footer and final CTA go dark with no dark-mode project and reading surfaces stay paper.

Components to mirror (anatomy read from registry source, style new-york-v4). shadcn sizes are desktop density (button and input h-9 = 36 px, checkbox 16 px); ExamLeaf needs 44 px targets (48 px for the main CTA) and 16 px input text. shadcn's input text is already `text-base md:text-sm`.

| Component | shadcn anatomy | React/Tailwind-only part | Plain-CSS / Django equivalent |
|---|---|---|---|
| Button | base `inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium`, focus `ring-[3px] ring-ring/50`, `disabled:opacity-50`; variants default, destructive, outline, secondary, ghost, link; sizes default h-9, xs h-6, sm h-8, lg h-10, icon size-9 (+xs/sm/lg) | cva, `asChild` Slot, `has-[>svg]` | `.btn` + `--secondary/--outline/--ghost/--danger/--link`, `--sm/--lg/--icon`; navigation uses `<a class="btn">`; min-height 44/48; loading = `aria-busy="true"` + spinner `::after` + `pointer-events:none` (stops double submit) |
| Input, Label, helper, error (Field) | input `h-9 w-full rounded-md border border-input px-3 py-1 shadow-xs`, focus `border-ring` + 3 px ring, `aria-invalid:border-destructive`; Label `text-sm font-medium`; FieldDescription muted; FieldError `role="alert" text-sm text-destructive`; FieldSet/Legend/Group | Radix Label, `data-slot` | style Django's `label`, `.helptext`, `.errorlist`; `input[aria-invalid="true"], input:user-invalid` (Chrome 119, Safari 16.5, Firefox 88); error text 14 px+ with an icon, never colour alone; border `--input` (3:1) |
| Select | two kinds: Radix Select (custom listbox in a portal) and NativeSelect (real `<select>`, `appearance-none`, chevron icon placed absolutely, `pr-9`, `<option>` coloured `Canvas/CanvasText`) | Radix Select | mirror NativeSelect only: `select{appearance:none;padding-right:2.25rem;background:var(--card) url("data:image/svg+xml,...") no-repeat right .8rem center/1rem}` (CSP allows `data:` images); keep the OS picker on phones |
| Checkbox, Radio | box `size-4 rounded-[4px] border-input`, checked `bg-primary text-primary-foreground`; radio `size-4 rounded-full` + 8 px dot; group `grid gap-3`; selectable card = FieldLabel wrapping a Field with `has-data-[state=checked]:border-primary bg-primary/5` | Radix roots, `data-state` | native inputs + `accent-color:var(--primary)`; wrapping label is the 44 px target (exists today); card: `label:has(input:checked){border-color:var(--primary);background:color-mix(...)}` for bundle, payment and shipping choices |
| Card | `flex flex-col gap-6 rounded-xl border bg-card py-6 text-card-foreground shadow-sm`; Header (grid, optional action column), Title `font-semibold leading-none`, Description muted, Content `px-6`, Footer | slot components | `.card` + children; one shadow layer; 16 px padding on phones, 24 px from 48rem; product card = `.card` + stretched link (R8) |
| Badge | `inline-flex rounded-full border px-2 py-0.5 text-xs font-medium`; default, secondary, destructive, outline, ghost, link | cva, Slot | `.badge` family (today's `.status`, `.kind`, tier chips); always a text label, 12 px minimum; interactive only if it is a link or button |
| Alert | `grid grid-cols-[0_1fr] has-[>svg]:grid-cols-[1rem_1fr] gap-x-3 rounded-lg border px-4 py-3 text-sm`; default (card) and destructive; Title `font-medium`, Description muted | cva | `.alert:has(> svg)`; Django `messages` map to `li.success/info/warning/error`; add the three extra variants from the extra tokens; `role="alert"` for errors, `role="status"` for the rest |
| Dialog, Alert Dialog, Sheet | overlay `fixed inset-0 bg-black/50`; content centred, `max-w-[calc(100%-2rem)] rounded-lg border bg-background p-6 shadow-lg`, 200 ms fade + zoom-95, close button top right, footer `flex-col-reverse sm:flex-row sm:justify-end`; Sheet slides 300/500 ms from an edge | Radix focus trap, portal, scroll lock, tw-animate-css | native `<dialog>` + `showModal()` (one delegated click handler in a static JS file) gives focus trap, Esc, inert page, `::backdrop`; animate with `@starting-style` + `transition ... allow-discrete` (Safari 17.5, Firefox 129; Chrome from memory); bottom-sheet variant on phones; not for primary flows |
| Tabs | list `bg-muted rounded-lg p-[3px] h-9`, trigger `data-[state=active]:bg-background`, "line" variant with `::after` underline | Radix roving tabindex | server tabs: `<nav class="tabs"><a aria-current="page">` (deep-linkable, no JS) for tiers and account pages; real ARIA tabs only if panels switch without reload (~30 lines JS) |
| Accordion | item `border-b`; trigger `flex justify-between py-4 text-sm font-medium hover:underline`; chevron rotates 180; content `animate-accordion-down/up` | Radix, keyframes | `<details name="faq"><summary>`; chevron on `summary::after`; exclusive groups: Chrome 120, Safari 17.2, Firefox 130 (Chrome docs); height animation optional (`::details-content` + `interpolate-size`, not verified here) |
| Toast | docs "Toast" points to Sonner (React); `toast.json` for new-york-v4 is a 404; Sonner icons per type, `--normal-bg: var(--popover)`, `--normal-border: var(--border)`, `--border-radius: var(--radius)` | Sonner, next-themes | Django messages as a fixed stack above the sticky bar, `role="status" aria-live="polite"`; success/info auto-hide in CSS (`animation:out .3s ease 5s forwards`, paused on hover and focus-within); errors persist; never move focus |
| Skeleton | `animate-pulse rounded-md bg-accent` (Tailwind pulse: opacity to .5 at 50%, 2 s) | Tailwind keyframes | `.skel{background:var(--muted);animation:pulse 2s cubic-bezier(.4,0,.6,1) infinite}`; opacity-only, so compositor work and cheaper than design.dev's gradient shimmer; `aria-hidden` on blocks, `aria-busy` on the container |
| Table | wrapper `relative w-full overflow-x-auto`; `w-full caption-bottom text-sm`; `th h-10 px-2 font-medium`, `td p-2`, `tr border-b hover:bg-muted/50`; caption muted | none | already close (`.table-scroll`); add `caption`, `th scope`, `tabular-nums` for marks and prices; keep the sticky last column |
| Breadcrumb | `nav aria-label="breadcrumb"` > `ol flex flex-wrap gap-1.5 text-sm text-muted-foreground sm:gap-2.5`; chevron separators; current page `text-foreground`; ellipsis item | Slot | `li + li::before{content:"/"}`; `aria-current="page"` on the last; use for Book > Paper > Solution |
| Pagination | `nav aria-label="pagination"`, `ul flex gap-1`, links reuse button variants (active = outline + `aria-current="page"`), Previous/Next text hidden on mobile | buttonVariants import | Django `Paginator` + `<a class="btn btn--ghost">`; only if a list grows (4 books and 30-paper grids need none) |
| Progress, stepper | Progress: track `h-2 rounded-full bg-primary/20`, indicator `bg-primary transition-all` shifted by `translateX(-(100-value)%)`. There is no Stepper component (0 hits in `llms.txt` and the sitemap) | Radix Progress | `<progress>` styled with `::-webkit-progress-value` / `::-moz-progress-bar`, or the `<ol class="stepper">` in R11 with `aria-current="step"` |
| Empty, Spinner | Empty: dashed border `p-6 md:p-12 text-center text-balance`, icon tile `size-10 rounded-lg bg-muted`, title `text-lg font-medium`, CTA slot. Spinner: Loader2 `animate-spin role="status"` | lucide icon | `.empty` for cart, order lookup, no-cover; spinner = SVG ring `animation:spin .8s linear infinite`, only inside pending buttons; reduced motion shows the words "Please wait" |
| Typeset | one CSS file inside `.typeset`, three controls: `--typeset-size`, `--typeset-leading` (1.75), `--typeset-flow` (1.25em); everything else derives | Tailwind import | same idea on `.prose` / `.question`: `--size:1.0625rem; --leading:1.65 (1.8 for :lang(as), :lang(bn)); --flow:1.1em` |

## 4. Fonts (Google Fonts only), with Bangla/Assamese

Sizes are woff2 as served to a Chrome-Android user agent (measured); a variable font is one file for all weights. Bangla files load only when the page contains Bangla characters, provided the `unicode-range` split is kept. Assamese needs U+09F0 (ৰ) and U+09F1 (ৱ), inside the Bengali subset range U+0980-09FE. Fontsource's language data (third party) lists Assamese for Hind Siliguri, Baloo Da 2, Tiro Bangla, Noto Sans Bengali and Anek Bangla; verify ৰ ৱ and conjuncts on a real low-end phone before committing.

| Family (weights) | Latin KB | Bangla KB (on demand) | Use |
|---|---|---|---|
| Hind Siliguri 400 / 600 / 700 | 7.8 / 7.9 / 7.6 | 39.3 / 38.7 / 34.9 | one family for Latin + Bangla + Assamese body text; cheapest Bangla for 1-2 weights (Noto Sans Bengali wins from 3 weights) |
| Noto Sans Bengali 400..700 (variable) | 25.1 | 105.4 (all weights) | system-grade Bangla fallback |
| Baloo Da 2 400..800 (variable) | 31.8 | 87.8 | rounded display with Bangla |
| Tiro Bangla 400 | 19.3 | 53.4 | serif Bangla for direction B headings |
| Anek Bangla 400..700 / Noto Serif Bengali 600..700 | 41.9 / 27.5 | 152.3 / 187.1 | too heavy, avoid |
| Poppins 700 / 800 (static) | 7.7 / 7.6 | none | headings; close to the covers' title lettering (compare visually) |
| Outfit 500..800 / Sora 500..800 / Plus Jakarta Sans 400..800 / Manrope 400..800 | 31.5 / 24.6 / 26.6 / 24.5 | none | geometric sans options |
| Rubik / Nunito Sans / DM Sans / Lexend / Inter (variable) | 34.5 / 30.2 / 36.1 / 38.8 / 47.3 | none | body options |
| Young Serif / DM Serif Display / Instrument Serif / Fraunces 600..700 / Playfair 600..800 / Literata / Source Serif 4 | 18.1 / 17.4 / 14.7 / 35.7 / 37.6 / 38.3 / 49.8 | none | serif display (direction B) |
| Atkinson Hyperlegible 400 / 700 | 10.9 / 11.1 | none | legibility first (the skill pairs it with Crimson Pro as "Academic/Research") |

- Cap: 2 families, 4 files, about 60 KB critical Latin. Poppins 800 + Hind Siliguri 400 + 600 = 23.3 KB (measured). If Hind's Latin shapes disappoint, use Plus Jakarta Sans (26.6 KB) for Latin and keep Hind Siliguri as the Bangla face. The skill states no font-count rule (all 74 of its pairings are exactly two families); the cap is ours.
- Self-host because of CSP. Google puts U+20B9 in `latin-ext` (17 of 17 families checked), so a price costs an extra request: subset once per file, e.g. `pyftsubset X.ttf --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+20B9,U+2122,U+2212" --flavor=woff2` (brotli 1.2.0 is already in the venv too). Keep a separate Bangla file in its own `@font-face` with Google's range `U+0951-0952,U+0964-0965,U+0980-09FE,U+200C-200D,U+25CC` and the same family name so it loads on demand.
- `font-display:swap`; preload only the Latin body and heading files; add a fallback `@font-face` using `size-adjust` and `ascent-override` against system-ui to cut layout shift; H1 `clamp(2rem,1.2rem + 3.6vw,3.25rem)` at 360 px.
- Bangla/Assamese text: `line-height` 1.7 or more; never `letter-spacing`, `text-transform:uppercase` or per-character splitting (it breaks conjuncts); reveal effects split on spaces only; set `lang` on every Assamese or Bangla element and style with `:lang(as), :lang(bn)`.
- Until the Assamese UI ships, names can fall back to the phone's own Bangla font at 0 KB (Android ships a Noto-family one; confirm on target devices); add the web file when the UI ships.

## 5. Three directions

### A. Midnight Stage (dark hero band + paper body; Modern Dark x Bento)
- Look: the navy header melts into a `#07122B` hero band with a static leaf-green radial spotlight behind a fanned stack of the four covers; paper below; gold only on numerals and seals; bento tiles for "what's inside".
- Palette "Midnight Leaf": Night #07122B, Brand #0B2A5B, Card-night #0E1D42, Leaf-glow #4CC265 (CTA, navy ink 8.2:1), Cover gold #EBC34A (11:1 on night), Muted-night #A9B8D6 (9.3:1), Paper #FBFAF7, Ink #1B2330.
- Fonts: Poppins 800 + Hind Siliguri 400/600 (23.3 KB Latin).
- Signature effect: cover stage (fan, one cover lifts on tap/hover, spine highlight) + a leaf conic-gradient border sweep on the hero CTA (2 loops, then rest) + a cross-document View Transition that morphs the tapped cover into its product page + bento tiles rising on view timelines.
- Cost: low (transform/opacity plus one small gradient repaint), JS 0 KB. Risk: the skill's Educational App profile lists dark modes as an anti-pattern, so dark stays on bands only.

### B. Paper & Leaf Press (editorial warm paper; Swiss/Academic x Warm Print)
- Look: exam-paper heritage: paper #FBFAF7 with a #F4EFE3 alternate, navy headings, hairline rules, "Q.1 Q.2 ..." numbered dividers, huge numerals ("30"), one marker highlight per section; the dark covers are the only dark objects, so they pop.
- Palette "Paper & Leaf": Paper #FBFAF7, Paper-alt #F4EFE3, Ink #1B2330, Navy #0B2A5B, Leaf-text #1A6E30, Leaf #2F8F3A (fills), Marker #FFE27A (ink on it 12.3:1), Gold-text #8A6508 (5.1:1).
- Fonts: Young Serif 400 (18.1 KB) or Fraunces 600..700 (35.7 KB) for headings + Hind Siliguri 400/600; Bangla headings in Tiro Bangla (19.3 KB + 53.4 KB on demand).
- Signature effect: marker underline drawn by a pseudo-element `scaleX(0 to 1)` on view-timeline entry (compositor only) and a cover lift with spine highlight; no blur or glow anywhere.
- Cost: lowest. Risk: can read as plain (the site is already paper + navy), so it needs scale contrast, one full-bleed navy band, and the marker as the single flourish.

### C. Subject Colour Blocks (bento + vibrant block; Playful Geometric with 2 px outlines)
- Look: four large subject tiles in the cover bases, each with the cover's pill colour as accent, 2 px ink outline + 4 px hard offset shadow, tier chips Easy/Medium/Hard echoing the cover bars, one tall tile in the bento.
- Palette "Subject Blocks": Physics #0F3560 + pill #88D4FA; Chemistry #134043 + #A0F4F9; Maths #2E1D65 + #81D0FB; Biology #124931 + #A2F8A6 (white on bases 10.4-14.2:1, pills on bases 7.6-9.1:1); ground #FBFAF7; ink #0A1226; gold #EBC34A for the "30" badge; CTA leaf #4CC265.
- Fonts: Outfit 500..800 (31.5 KB) + Hind Siliguri 400/600; Baloo Da 2 where a rounded Bangla display face is wanted (31.8 + 87.8 KB).
- Signature effect: "sticker press": the hard shadow collapses and the tile moves 3 px on `:active`; tiles rest at +/-1 degree and straighten on hover/tap; a per-subject `view-transition-name` morphs a tile into its book page.
- Cost: low. Risk: the skill rates Vibrant & Block and Neubrutalism unsuitable for formal or conservative audiences, and parents buy too: keep radius 12 px, body text on paper, outlines 2 px.

Recommended: A's bands (hero, footer, final CTA) + B's paper body and marker + C's subject colours used only for tiles, chips and view-transition names.

## 6. Palettes and contrast (WCAG ratios computed here)

| Pair | Ratio | Verdict |
|---|---|---|
| white on #2F8F3A (today's leaf) | 4.11 | fails 4.5 for text; only large or bold text (3:1) |
| white on #1A6E30 | 6.33 | pass; use for light-surface CTAs |
| ink #07122B on #4CC265 | 8.15 | pass; use for CTAs on night bands |
| #4CC265 on #07122B / on #0B2A5B | 8.15 / 6.16 | pass (links on dark) |
| #EBC34A on #07122B / on #0B2A5B / on paper | 11.0 / 8.31 / 1.62 | pass on dark; fails on paper, so gold is fills and dark-band numerals only |
| #8A6508 on paper; #1A6E30 on paper | 5.10; 6.07 | pass (gold text, leaf text) |
| #5D6675 on paper / on #F1F3F6 | 5.55 / 5.21 | pass (muted text) |
| #EAF1FF on #07122B; #A9B8D6 on #07122B / #0B2A5B | 16.4; 9.3 / 7.0 | pass |
| input border #B9C0CA (today) / #7B8595 on white | 1.83 / 3.73 | today fails the 3:1 control-boundary rule; use #7B8595 |
| focus ring #2F8F3A on paper / white; #8FD694 on night | 3.94 / 4.11; 10.8 | pass |
| #B42318 on paper; ink #1B2330 on marker #FFE27A | 6.30; 12.34 | pass |
| shadcn Green light #FFF1F2 on #16A34A | 3.00 | fails; its dark pair #052E16 on #22C55E = 6.54 passes |

Keep tokens as hex (works in old WebViews); use OKLCH or `color-mix()` only with a hex line before it. Skill palette rows used as reference only: Academic Journal #1E3A5F + #B45309, E-commerce #059669 + #EA580C, LMS #0D9488 + #D97706, E-commerce Luxury #1C1917 + #A16207.

## 7. Motion rules (ui-ux-pro-max motion.csv and UX rules, Modern Dark pack, Swiss and Warm Print packs)

- Tokens: `--t-press:120ms` (feedback within 100-150 ms; Swiss pack uses 120 ms linear); `--t-hover:200ms` (skill: 150-200 subtle, 200-300 standard); reveal 300-400 ms subtle or 400-600 ms standard (view timelines ignore duration); page change exit 140 ms, enter 220 ms (skill: exit about 60-70% of enter, cap about 250 ms, never block navigation).
- Easings: `--ease-out:cubic-bezier(.16,1,.3,1)` (Modern Dark expo-out) for entrances and reveals; `cubic-bezier(.65,0,.35,1)` for page changes; `cubic-bezier(.34,1.56,.64,1)` only on small controls (skill: no back.out on dense or informational UI); linear only for spinners and loops.
- Distance and count: offsets 8-16 px (24 px max); stagger 30-40 ms per item (60-80 ms for cards), at most 8 items. In CSS prefer one `view()` timeline per element, which staggers naturally without delays.
- Budget: at most 1-2 animated elements per view; continuous animation only for loading; parallax 5-15% depth, never on body copy and not on phones; no auto-rotating content (if unavoidable: previous/next + pause, stops on focus, hover and reduced motion).
- Properties: transform and opacity only; never width, height, top, left, box-shadow or blur in keyframes; `will-change` only on the 1-2 layers animating; never hide the LCP element behind `opacity:0` (fully transparent elements are not LCP candidates, so the delay becomes the LCP time).
- Reduced motion: wrap every non-essential keyframe in `@media (prefers-reduced-motion: no-preference)` so the default state is the final readable state; keep colour, focus and press feedback; marquees become a hand-scrollable row.
- Capability gates: `@supports (animation-timeline: view())` for scroll-driven effects; `@view-transition` inside the no-preference query; `@property` effects degrade to a static gradient.
- Data saver: Chrome-family browsers send `Save-Data: on`; Django can add `Vary: Save-Data`, drop decorative classes and serve 240w covers (from memory; not checked on Samsung or UC browsers).

## 8. Pattern recipes (plain CSS and vanilla JS; no inline script; motion inside the no-preference query)

R1 Hero layouts. (a) Stage: two columns from 48rem (copy, CTAs, trust row | fan of four covers); on phones the fan sits under the H1. (b) One spotlight cover. (c) Scroll-snap strip on phones: `display:grid;grid-auto-flow:column;grid-auto-columns:42%;overflow-x:auto;scroll-snap-type:x mandatory`. First cover `fetchpriority="high"` with `width`/`height`; `<picture>` AVIF > WebP > PNG; `srcset` 240/320/480w.
```css
.fan{display:flex;justify-content:center}.fan li{list-style:none;width:min(30vw,168px);margin-inline:-5vw}
.fan li:nth-child(1){transform:rotate(-8deg) translateY(12px)}.fan li:nth-child(2){transform:rotate(-3deg)}
.fan li:nth-child(3){transform:rotate(3deg)}.fan li:nth-child(4){transform:rotate(8deg) translateY(12px)}
@media(hover:hover){.fan li{transition:transform .2s var(--ease-out)}.fan li:hover{transform:translateY(-10px);z-index:2}}
.cover{position:relative;border-radius:6px;box-shadow:0 14px 24px -14px #000}   /* one shadow layer */
.cover::after{content:"";position:absolute;inset:0;border-radius:inherit;background:linear-gradient(90deg,rgb(0 0 0/.28),transparent 7%,transparent 93%,rgb(255 255 255/.07))} /* spine */
.hero::before{content:"";position:absolute;inset:0;background:radial-gradient(60% 55% at 50% 38%,rgb(76 194 101/.3),transparent 70%)} /* spotlight: gradient, no blur filter */
```
R2 Bento "What's inside" (30 papers, 10/10/10 tiers, board pattern, QR solutions, marking scheme, price and COD):
```css
.bento{display:grid;gap:12px;grid-template-columns:repeat(2,1fr)}.bento>*{padding:16px;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--card)}
.bento .wide{grid-column:span 2}.bento .tall{grid-row:span 2}@media(min-width:56rem){.bento{grid-template-columns:repeat(4,1fr)}}
```
R3 Spotlight and gradient borders. Static: `border:2px solid transparent;background:linear-gradient(var(--card),var(--card)) padding-box,linear-gradient(135deg,var(--primary),#88D4FA) border-box`. Animated sweep, one element only: `@property --a{syntax:"<angle>";inherits:false;initial-value:0deg}`, `conic-gradient(from var(--a),transparent 0 70%,#EBC34A,#4CC265 90%,transparent)` as the border-box layer, `animation:sweep 3s linear 2`, `@keyframes sweep{to{--a:360deg}}`; browsers without `@property` keep a static border. Pointer spotlight, desktop only (`@media (hover:hover) and (pointer:fine)`): about 6 lines of JS set `--x` and `--y` on `pointermove` with `el.style.setProperty` (CSSOM, allowed under this CSP) and CSS paints `radial-gradient(240px circle at var(--x) var(--y),rgb(76 194 101/.16),transparent 70%)`.
R4 Marquee. Four covers are too few; use the fan or the snap strip. A marquee suits chapter-name chips or quotes (to marquee the covers anyway, repeat the set until each half is wider than the widest viewport):
```css
.mq{overflow:hidden;-webkit-mask-image:linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent);mask-image:linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent)}
.mq ul{display:flex;gap:12px;width:max-content;margin:0;padding:0;list-style:none}  /* list rendered twice; 2nd copy aria-hidden */
@media(prefers-reduced-motion:no-preference){.mq ul{animation:mq 40s linear infinite}.mq:hover ul{animation-play-state:paused}}@keyframes mq{to{transform:translateX(calc(-50% - 6px))}}
```
R5 Counters. Real numbers stay in the markup as static text ("30", "120", "4"); the covers already say "30 Papers Inside". A count-up, if wanted, is IntersectionObserver + rAF over 600 ms (about 25 lines) that starts from the printed value, so no-JS and reduced motion show the truth. Only true, dated numbers.
R6 Scroll reveal, CSS only and visible by default, so it is no-JS safe:
```css
@supports (animation-timeline:view()){@media(prefers-reduced-motion:no-preference){.reveal{animation:rise linear both;animation-timeline:view();animation-range:entry 0% entry 45%}@keyframes rise{from{opacity:0;transform:translateY(16px)}}}}
```
The marker underline (direction B) is the same rule on a `::after` going from `transform:scaleX(0)` to `scaleX(1)`.
R7 Sticky CTA (product page, phones):
```css
.buybar{position:fixed;inset:auto 0 0;display:flex;gap:12px;align-items:center;justify-content:space-between;padding:10px 16px calc(10px + env(safe-area-inset-bottom));background:var(--secondary);color:var(--secondary-foreground);z-index:30}
@media(min-width:48rem){.buybar{display:none}}@media(max-width:47.99rem){body:has(.buybar){padding-bottom:5rem}html{scroll-padding-bottom:5rem}}
```
Price + "Add to cart"; `scroll-padding` stops a focused field hiding under it (WCAG 2.2 focus not obscured). The messages stack sits above it.
R8 Product card, whole card one link:
```css
.pcard{position:relative;display:grid;gap:8px}.pcard a::after{content:"";position:absolute;inset:0}
.pcard img{aspect-ratio:480/678;width:100%;height:auto;border-radius:6px}.price{font-variant-numeric:tabular-nums}
@media(hover:hover){.pcard img{transition:transform .2s}.pcard:hover img{transform:translateY(-4px)}}.pcard:active img{transform:scale(.98)}
```
MRP struck through plus "Save Rs. X (Y%)" as text, never colour alone; "Only 3 left" only when stock says so.
R9 Bundle and option cards (one book / any two / all four; COD vs UPI), radios inside labels, no JS:
```css
.opt{display:flex;gap:12px;padding:14px;border:2px solid var(--border);border-radius:var(--radius-md);background:var(--card)}
.opt:has(input:checked){border-color:var(--primary);background:var(--accent)}.opt:has(input:focus-visible){outline:3px solid var(--ring);outline-offset:2px}
```
The best-value bundle gets a badge and a server-computed saving; show real totals.
R10 FAQ: `<details name="faq"><summary>Question</summary><p>Answer</p></details>`; `summary{display:flex;justify-content:space-between;align-items:center;min-height:48px;list-style:none;cursor:pointer;font-weight:600}`, `summary::-webkit-details-marker{display:none}`, `summary::after` is a rotated 8 px border chevron and `details[open] summary::after{transform:rotate(-135deg)}`. Add FAQPage JSON-LD only if the answers match the visible text.
R11 Checkout stepper: `<ol class="stepper" aria-label="Checkout"><li class="done">Cart</li><li aria-current="step">Delivery</li><li>Pay</li></ol>`
```css
.stepper{display:flex;gap:8px;margin:0;padding:0;list-style:none;counter-reset:s}.stepper li{flex:1;counter-increment:s;padding-top:6px;border-top:4px solid var(--border);font-size:.875rem;color:var(--muted-foreground)}
.stepper li::before{content:counter(s) ". "}.stepper .done,.stepper [aria-current=step]{border-color:var(--primary);color:var(--foreground)}.stepper [aria-current=step]{font-weight:700}
```
Past steps link back. Guest checkout first; `autocomplete` on every field, `inputmode="numeric"` for PIN, `type="tel"` for phone; validate on blur with `:user-invalid`; after a failed submit focus a linked error summary; submit button `aria-busy` and disabled. Confirmation: check icon drawn by `stroke-dashoffset` over 600 ms, no confetti.
R12 Empty states and skeletons: `.empty{padding:2rem 1rem;border:2px dashed var(--border);border-radius:var(--radius-xl);text-align:center;text-wrap:balance}` for the empty cart ("Browse the four books"), an order-lookup miss ("Check the number or email") and no-cover. Skeleton = the pulse in section 3; reserve image space with `aspect-ratio` and a per-subject background class.
R13 View transitions (MPA, no JS):
```css
@media(prefers-reduced-motion:no-preference){@view-transition{navigation:auto}::view-transition-old(root){animation-duration:.14s}::view-transition-new(root){animation-duration:.22s}.vt-physics{view-transition-name:cover-physics}}
```
Same class on the list-card image and the product-page image (one unique name per book per page). Chrome/Edge 126, Safari 18.2, not Firefox; unsupported browsers simply navigate.
R14 Testimonials and trust badges. Real quotes only (name, class, town, with consent); until they exist show a proof strip (sample page, board pattern, marking scheme, free QR solutions, publisher name). Layout: scroll-snap rail (`display:grid;grid-auto-flow:column;grid-auto-columns:85%;overflow-x:auto;scroll-snap-type:x mandatory`), next card peeking, no autoplay. Badges: a `ul` of 20 px SVG + 14 px text (Assam Board pattern, free QR solutions, secure payment through Razorpay, cash on delivery where allowed, GST invoice), limited to what the Refunds, Shipping and Terms pages actually promise; use Razorpay marks as their guidelines require.
R15 Native dialog: `dialog{border:0;border-radius:var(--radius-md);padding:24px;max-width:min(32rem,calc(100% - 2rem));background:var(--card);color:var(--card-foreground)}dialog::backdrop{background:rgb(0 0 0/.5)}` plus one delegated click handler (`e.target.closest('[data-dialog]')`, then `document.getElementById(id).showModal()`) in a static JS file; for "remove item" and "cancel order" confirms only.

## 9. Feasibility matrix: CSS-only vs JS, and cost on a low-end phone

Original mechanics were read from the Aceternity registry source unless noted. Support is from caniuse (global usage, not India-specific) and the checks cited in section 11.

| Effect (source) | How the original works | Pure-CSS route (min browsers) | JS | Low-end cost | Verdict |
|---|---|---|---|---|---|
| Infinite Moving Cards / marquee (Aceternity) | keyframes `translate(calc(-50% - .5rem))` 20/40/80 s linear, `mask-image` edge fade, children duplicated in JS, `animation-play-state` on hover | keyframes + mask-image (`-webkit-` prefix before Chrome 120 / Samsung 25) | none, duplicate in the template | free (transform) | ship for chips and quotes |
| Spotlight hero (Aceternity) | SVG ellipse + blur filter, 2 s keyframes after a 0.75 s delay | radial-gradient pseudo-element + one-shot fade | none | gradient free; SVG blur costly | ship as a gradient |
| Card Spotlight, Glowing Effect, Glare Card | pointermove + rAF writing CSS variables; `mask-composite`, repeating conic-gradient, `background-attachment:fixed` | radial or conic gradient driven by `--x/--y` | about 10 lines | moderate; inert on touch | desktop only |
| Moving Border, Hover Border Gradient | SVG `getPointAtLength` every rAF frame; `setInterval` swapping gradients | `@property --a` + conic-gradient (Chrome 85, Safari 16.4, Firefox 128) | none | paint per frame on one small element | one CTA, 2 loops |
| Text Generate Effect | per-word spans, Motion stagger 0.2 s, blur 10px to 0, 0.5 s | per-word `animation-delay` through `:nth-child`, opacity only | none | blur animation rasterises; animated H1 delays LCP | skip on H1; sub-line fade-up only |
| Hero Parallax, Container Scroll, Sticky Scroll Reveal, Tracing Beam, Timeline | Motion `useScroll/useTransform/useSpring/useMotionValue` on the main thread (all five read) | `animation-timeline: view()/scroll()` + `position:sticky` (Chrome/Edge 115, Safari 26, Firefox behind a flag) | none | transform/opacity can run off the main thread | ship subtle (16 px), `@supports`-gated |
| Page transitions (animmaster category) | not public | `@view-transition{navigation:auto}` (Chrome/Edge 126, Safari 18.2) | none | snapshot cost; keep under 250 ms | ship (cover morph) |
| Aurora Background, Background Gradient Animation | Aurora: `repeating-linear-gradient` at 300% + `blur(10px)` + `mix-blend-difference` + background-position keyframes; Gradient Animation: five blobs + SVG goo filter + pointer follow | Aurora is CSS-only | pointer JS for the other | large blurred, blended layer repaints every frame | skip (also the "AI gradient" look) |
| Beams, Wavy, Sparkles, Meteors (read); Vortex, Shooting Stars (not read) | SVG + Motion; canvas + simplex-noise with `ctx.filter=blur(10px)` full screen; tsparticles; CSS meteors with random delays | meteors only | libraries | full-screen canvas blur prohibitive; meteors cheap but meaningless | skip |
| Glare Card, Floating Dock (read); 3D Card, Wobble, Tilted, 3D Pin (Pro or not read; the site describes mouse-driven tilt) | pointer-driven rotation through CSS variables; `useSpring` magnify by cursor distance | static `transform:perspective(800px) rotateY(-8deg)` | pointer JS | no hover on touch | static tilt only |
| Card Hover Effect, Focus Cards | shared `layoutId` hover background; siblings `blur-sm scale-[.98]` | `:hover` + `:has()` with opacity instead of blur (Chrome 105, Safari 15.4, Firefox 121) | none | blur on siblings rasterises; opacity free | opacity version, hover only |
| Bento Grid | Tailwind grid, `hover:shadow-xl`, `group-hover:translate-x-2` | CSS grid | none | free | ship |
| Carousels (Apple Cards: native scroll container + `scrollBy` buttons; Animated Testimonials: `setInterval` autoplay + drag; animmaster sliders not public) | Motion `AnimatePresence`, drag, autoplay | `scroll-snap` (Chrome 69, Safari 11, Firefox 68) | prev/next, about 6 lines | free | ship without autoplay |
| Three.js and WebGL (ThreeUI; 19 animmaster shaders; Aceternity globes) | WebGL | none | libraries | prohibitive on 2-3 GB phones | skip |
| Frosted header (`backdrop-filter`) | n/a | `backdrop-filter:blur(8px)` (Chrome 76, Safari 9, Firefox 103) with a solid `@supports not` fallback | none | re-blurs each scroll frame | one sticky element at most |
| Accordion, dialog, tabs, popover | Radix | `<details name>`, `<dialog>`, `popover`, link tabs | `showModal()` one-liner | free | ship |
| Enter/exit animation for dialogs, popovers, menus | Radix `data-state` + tw-animate-css (fade, zoom-95, slide) | `@starting-style` + `transition-behavior:allow-discrete` (Safari 17.5, Firefox 129; Chrome from memory) | none | free (opacity/transform) | ship; no animation where unsupported |
| Skeleton | shadcn pulse; design.dev shimmer 1.8 s | opacity pulse or gradient shimmer | none | pulse = compositor; shimmer = paint | ship the pulse |
| Animated counter | Motion/GSAP | `@property <integer>` + `counter()` | optional | paint | skip; static numbers |

Global caniuse share: view transitions 91.8%, cross-document 86.0% (+1.8% partial), container queries 94.8%, `:has()` 94.8%, backdrop-filter 96.4%, AVIF 95.4%. UC Browser lacks `:has()`, container queries and view transitions; Opera Mini supports almost none of this. Every effect is therefore an enhancement over a page that already works static.

## 10. Do-not rules (from the skill's guidelines, its reasoning data, and our measurements)

1. No emoji as icons (skill `no-emoji-icons`): one SVG sprite (Lucide, Phosphor or Heroicons), one stroke width, `aria-hidden` when beside text.
2. No generic AI look: purple/pink or aurora gradients, glow blobs, neon, multi-layer or 3D shadows, ornament. The skill's anti-pattern counts across 192 profiles: excessive decoration 29, complex shadows 21, 3D effects 21, AI purple/pink gradients 14 (trust-heavy categories). It also flags muted colours / low energy (18) in learning products, so avoid grey-on-grey. Colour comes from the covers: navy, teal, indigo, emerald, gold, leaf.
3. No more than 2 font families and about 60 KB of fonts; never letter-spacing, uppercase or per-character animation on Bangla/Assamese; no Google Fonts CDN (CSP) and no price page that triggers a `latin-ext` fetch.
4. No animation of layout properties or blur; at most 1-2 animated elements per view; every effect behind `prefers-reduced-motion: no-preference` and `@supports`; no auto-rotating carousels or decorative infinite loops; never hide the LCP element.
5. No hover-only affordances; touch targets 44 px (WCAG 2.2 minimum is 24 px, the skill says 44/48), 8 px gaps; focus ring 3 px at 3:1; `scroll-padding` for every sticky bar.
6. No placeholder-only labels; error next to the field with `aria-describedby` plus a focused summary; no colour-only state (add icon or text); no control border under 3:1 (today's 1.83:1).
7. No white text on #2F8F3A (4.11:1): white on #1A6E30 (6.3:1) or navy ink on #4CC265 (8.2:1).
8. No PNG covers (689 KB for four): AVIF/WebP with `srcset`, `width`/`height` and `aspect-ratio`; no layout shift.
9. No fake proof: invented reviews, unverifiable counters, urgency not backed by stock; badges only for promises the policy pages make.
10. No modal for a primary flow; no custom select listbox; no `100vh` (use `dvh`); no dark body for reading surfaces (the skill's Educational App profile lists dark modes as an anti-pattern): dark bands only.
11. No new runtime libraries (React, Tailwind, Motion, GSAP, Three.js, tsparticles) and no third-party CDN beyond what CSP already allows.

## 11. Sources, method and limits

- ui-ux-pro-max-skill: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill, `git clone --depth 1` at 15cc30a (2026-10-07). Read `.claude/skills/ui-ux-pro-max/SKILL.md`, `references/quick-reference.md`, `references/pro-rules.md`, README, CLAUDE.md, and `src/ui-ux-pro-max/data/` (styles, landing, motion, ux-guidelines, typography, colors, products, ui-reasoning, google-fonts, stacks/html-tailwind). Ran `search.py` about 25 times. Its CLAUDE.md is contributor guidance for that repo and was not followed.
- shadcn/ui: https://ui.shadcn.com/docs/theming.md, /docs/components, /docs/typeset.md, /llms.txt, /r/index.json (63 UI items), /r/styles/new-york-v4/<component>.json (27 read), /r/themes.css. The `/themes` page returned no readable content to WebFetch, and the individual component doc pages were not read one by one: anatomy comes from registry source, the component index from `llms.txt`.
- ThreeUI: https://threeui.com/browse, /pricing, /sitemap.xml. Aceternity: https://ui.aceternity.com/, /pricing, /sitemap.xml, /registry/<name>.json (32 read; 2 returned 401). animmasterlib: https://animmasterlib.dev/ and scroll, hovers, hero, grids pages, /sitemap.xml (counts only).
- designprompts.dev: https://www.designprompts.dev/ (SPA); read /sitemap.xml and the public bundle /assets/index-FHds4wvP.js (32 style definitions parsed). design.dev: https://design.dev/, /llms.txt, /guides/scroll-timeline/, /ai/prompts/skeleton-loading-screen/, /ai/prompts/style-packs/warm-print-magazine/ and /swiss-editorial/, /guides/fable-web-design/. superdesign: https://superdesign.dev/library, /llms.txt, /sitemap-pages.xml (slugs only).
- Support data: caniuse JSON from github.com/Fyrd/caniuse (features-json); Chrome docs for the exclusive accordion (Chrome 120, Firefox 130, Safari 17.2); web searches for scroll-driven animations (Chrome/Edge 115, Safari 26, Firefox flag), `@starting-style` (Safari 17.5, Firefox 129), `@property` (Firefox 128, Safari 16.4), cross-document view transitions (Chrome 126, Safari 18.2), `color-mix()` (Chrome 111, Firefox 113, Safari 16.2) and `:user-invalid` (Chrome 119, Firefox 88, Safari 16.5). Not verified: `::details-content`, `interpolate-size`, `allow-discrete` in Chrome, Save-Data on Samsung and UC browsers, Android's system Bangla font.
- Font sizes and subsets: Google Fonts CSS2 API plus `Content-Length` of each woff2 (Chrome-Android user agent), and the unicode-range of every served subset (2026-10-08). Language coverage: Fontsource "about" pages for Hind Siliguri, Baloo Da 2, Tiro Bangla, Noto Sans Bengali, Anek Bangla (third party).
- Local files: `examleaf-web/static/css/site.css`, `templates/base.html`, `home.html`, `shop/product.html`, `examleaf/settings.py` (CSP), `shop/views.py` (Razorpay CSP), `static/img/*.png` (re-encoded in a scratch folder only, nothing written to the repo), Django's `forms/boundfield.py`.
- Limits: no effect was run on a device, so cost labels are qualitative; test on a real entry-level Android with Lighthouse mobile (slow 4G, 4x CPU) before locking budgets. The designprompts.dev and superdesign pages are client-rendered, so their on-screen content was not reviewed visually. Licences were noted only where a page states them (skill MIT, fonts OFL, paid tiers); no legal review.
- Open decisions for the founder: dark bands only or a full dark theme; whether real reviews exist yet; approval to replace the cover PNGs with AVIF/WebP.
