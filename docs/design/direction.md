# ExamLeaf redesign — direction and shared vocabulary (decided 2026-10-08)

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

The direction and shared vocabulary of the website's first redesign, decided on 8 October 2026 from [the resources
brief](resources-brief.md). It is kept as a record: the website was restyled again by the Answer Script redesign
([answer-script-implementation.md](answer-script-implementation.md)).

Source: `resources-brief.md` (the digest of ui-ux-pro-max, shadcn/ui, ThreeUI, Aceternity, animmasterlib, designprompts, design.dev, superdesign). This file is the contract between the designer (Design canvas) and the builders (Django templates + one CSS file). Both sides use exactly these names.

## 1. Direction: "Midnight Stage" bands, paper body, subject tiles
- **Bands** (header, hero, final call-to-action, footer): night `#07122B` melting from the navy header, a static leaf-green radial spotlight behind a fanned stack of the four covers; gold `#EBC34A` only for numerals and seals on dark; muted text on dark `#A9B8D6`.
- **Body**: warm paper `#FBFAF7` with alternate `#F4EFE3`, ink `#1B2330`, navy headings, hairline rules, exam-paper cues (Q.1 / Q.2 numbered dividers, big numerals such as "30"), one marker highlight `#FFE27A` per section as the single flourish.
- **Subject colour** only on tiles, chips and view-transition names: Physics `#0F3560` + `#88D4FA`, Chemistry `#134043` + `#A0F4F9`, Maths `#2E1D65` + `#81D0FB`, Biology `#124931` + `#A2F8A6`. Tier chips Easy `#1B7F3B`, Medium `#1A5FB4`, Hard `#A0272D` (white text, bold).
- **Fonts** (self-hosted and subset on the real site; Google Fonts link in the canvas): headings Poppins 700/800; body Hind Siliguri 400/600 (covers Assamese/Bangla script; `line-height ≥ 1.7`, never letter-spacing or uppercase on Bangla text). If Hind's Latin looks weak in the canvas, body becomes Plus Jakarta Sans 400/600 with Hind Siliguri kept for Bangla ranges. Two families, at most four files, about 60 KB.
- **Radius** 12 px (cards, tiles, inputs), 999 px for chips. Shadows: one soft shadow on cards (`0 1px 2px rgba(11,42,91,.06), 0 8px 24px rgba(11,42,91,.08)`), hard 4 px offset only on subject tiles. No glow, no blur, no multi-layer shadows, no gradient washes.
- **Motion**: transform and opacity only, 150–250 ms, `cubic-bezier(.2,.7,.2,1)`; at most two effects per view; everything inside `@media (prefers-reduced-motion: no-preference)` and `@supports`; never animate the largest content element. Signature effects: cover stage (one cover lifts on hover/tap), marker underline drawn on entry, subject tile "sticker press" on `:active`, view transition from a tile or cover to its page. No JavaScript needed for any of them.
- **Images**: covers served as AVIF/WebP at 320 and 480 widths with PNG fallback.

## 2. Token layer (shadcn names, hex values; `:root` light, `.band-night` and `[data-theme=dark]` override)
```
--background #FBFAF7   --foreground #1B2330   --card #FFFFFF        --card-foreground #1B2330
--primary #0B2A5B      --primary-foreground #FFFFFF
--secondary #F4EFE3    --secondary-foreground #1B2330
--muted #F1F3F6        --muted-foreground #5D6675
--accent #1A6E30       --accent-foreground #FFFFFF      (on night bands: --accent #4CC265, --accent-foreground #07122B)
--destructive #B42318  --destructive-foreground #FFFFFF
--border #D9DDE3 (hairlines)   --input #7B8595 (control borders, 3.7:1)   --ring #2F8F3A (focus, 2 px + 2 px offset)
--night #07122B   --night-card #0E1D42   --night-muted #A9B8D6   --gold #EBC34A   --gold-text #8A6508   --marker #FFE27A
--physics #0F3560 --chemistry #134043 --maths #2E1D65 --biology #124931   --easy #1B7F3B --medium #1A5FB4 --hard #A0272D
--radius 12px
```
Contrast rules: white text only on `--primary`, `--accent`, `--destructive`, tiers and subject bases (all ≥ 4.5:1); gold is never text on paper; `--leaf` `#2F8F3A` is fills and focus rings only.

## 3. Component vocabulary (class names the builders implement and the designer draws)
| Class | Anatomy and states |
|---|---|
| `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-destructive` / `.btn-accent`; sizes `.btn-sm` `.btn-lg`; `.btn-block` | 44 px min height, 16 px side padding, radius 10 px, bold label, optional leading inline SVG icon 20 px; hover darkens 6 %, `:active` translates 1 px, `:focus-visible` ring, `[aria-busy]` shows a spinner |
| `.field` → `label`, control, `.field-help`, `.field-error` | 48 px controls, border `--input`, `[aria-invalid=true]` red border and error text with an icon; required marker |
| `.input` `.select` `.textarea` `.checkbox` `.radio` `.switch` `.otp` (6 boxes) | native elements styled; `.otp` is six `inputmode=numeric` boxes |
| `.card` → `.card-header` `.card-body` `.card-footer` | white, radius 12, soft shadow, 20 px padding; `.card-interactive` lifts on hover |
| `.badge` + `.badge-easy` `.badge-medium` `.badge-hard` `.badge-gold` `.badge-muted` | 999 radius, 12 px bold, 24 px tall |
| `.alert` + `.alert-info` `.alert-success` `.alert-warning` `.alert-error` | left icon, title, text; no left border bar |
| `.toast` region (Django messages) | top-right on desktop, bottom on phone, dismiss button |
| `dialog.dialog` | native `<dialog>` with backdrop, header, body, footer |
| `.tabs` (radio-based) | underline indicator |
| `details.accordion` | summary with chevron rotating |
| `.skeleton` | shimmer-free pulse (opacity) |
| `.table-wrap > table.table` | horizontal scroll box, sticky header |
| `.breadcrumb`, `.pagination` | links, current page `aria-current` |
| `.stepper` → `.step` `.step-done` `.step-current` | checkout: Address → Delivery → Payment → Done |
| `.tile` + `.tile-physics` … | subject tile: cover base colour, pill accent, 2 px ink outline, 4 px hard shadow, sticker press |
| `.band` `.band-night` | full-bleed dark section with inverted tokens |
| `.stage` | fanned cover stack (3–4 `img.stage-cover`) |
| `.marker` | highlighted phrase |
| `.price` → `.price-now` `.price-mrp` `.price-save` | ₹ with the rupee glyph from the subset font |
| `.empty` | empty state: inline SVG, title, text, one button |
| `.timeline` → `.timeline-item` (`.done` `.current`) | order status |
| `.qr-card` | QR landing header: paper code, subject, tier, "scan verified" seal |
| `.nav` `.nav-toggle` `.nav-menu` | header; one row at every width with a Menu button under 900 px |
| `.footer` | night band: columns, legal links, publisher line |

## 4. Pages (artboards in the canvas, then templates)
Desktop 1280 wide: Home · Book (subject) · Solutions (paper) · Shop catalogue · Product · Cart · Checkout · Order status (token link) · Login (phone OTP, email code, Google, passkey) · Register (student; under-18 parent fields) · My account/record · 404. Phone 390×844: Home · Checkout · Solutions. Email 600 wide: order confirmation.

## 5. Do-not list (binding)
No emoji or mixed icon sets (one inline stroke-SVG set, 1.75 px stroke). No gradient washes, glow, 3D, WebGL. No Google CDN fonts on the real site (CSP; self-host). No white text on `#2F8F3A`. No control border under 3:1. No hover-only actions. No target under 44 px. No PNG covers in production. No letter-spacing/uppercase on Bangla. No animation of the largest content element. No more than two effects per view.
