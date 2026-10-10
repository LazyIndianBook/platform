# ExamLeaf components, as drawn

![Component](../assets/badges/component-website.svg) ![Status](../assets/badges/status-archive.svg) ![For developers](../assets/badges/audience-developers.svg)

The component spec of the website's first redesign, drawn on the Design canvas on 8 October 2026 and built into the
Django templates, with a section on what the Next.js frontend built from it. It is kept as a record: the Django pages
were removed in Phase 8, and the website was restyled again by the Answer Script redesign
([answer-script-implementation.md](answer-script-implementation.md)).

The spec the Django builder implements. Drawn on the Design canvas (https://claude.ai/artifact/Qzy2yAjvNy3Fq12mYZv6Yu, 16 artboards); every artboard carries these class names on its markup. Tokens are in `tokens.css` (include it first in `site.css`); names follow `direction.md` section 3. Sizes are CSS px as drawn. "Phone" means under 900 px wide unless a width is given.

**Contents**

- [0. Page-level layout](#0-page-level-layout)
- [1. Components (direction section 3, in its order)](#1-components-direction-section-3-in-its-order)
- [2. Drawn patterns that sit beside the vocabulary](#2-drawn-patterns-that-sit-beside-the-vocabulary)
- [3. Pages (artboard → template)](#3-pages-artboard--template)
- [4. Motion: docs/design/motion.md](#4-motion-docsdesignmotionmd)
- [4a. Craft pass (2026-10-08): what the built site does beyond the drawings](#4a-craft-pass-2026-10-08-what-the-built-site-does-beyond-the-drawings)
- [5. Canvas-only levers](#5-canvas-only-levers)
- [5. As built (2026-10-08, canvas pass against the Next.js frontend)](#5-as-built-2026-10-08-canvas-pass-against-the-nextjs-frontend)

## 0. Page-level layout

| Rule | Value |
|---|---|
| Page shell | `body > header.nav, ul.toast, main, [section.band-night], footer.footer`. Body is a flex column, `min-height: 100vh`; `main { flex: 1 0 auto }`, so the footer stays at the bottom of short pages (Log in, 404). |
| Container | `.container { width: 100%; max-width: calc(var(--container) + 48px); margin-inline: auto; padding-inline: var(--gutter); box-sizing: border-box }`. That gives 1120 px of content on desktop and a 16 px gutter on a 390 px phone. |
| Header | 64 px min-height, one row at every width (see `.nav`). |
| Section rhythm | `.section { padding-block: var(--section) }`: 96 px on desktop, 64 px on phones. A page that opens with a breadcrumb or a form starts 24–32 px under the header (48–64 px for a centred form) and ends at 96. Sections alternate `--background` and `--secondary`; never two `--secondary` in a row. Dark bands only for the header, hero, final call to action and footer. |
| Gutters | 24 px (`--gap`) between cards and columns. In forms, 16 px between rows and 20 px between columns. 16 px between paper links and between a dense list's items, 12 px between buttons, 8 px between chips. |
| Grids | Intrinsic, no breakpoints: `grid-template-columns: repeat(auto-fit, minmax(min(N, 100%), 1fr))`. N = 240 (subject tiles, product cards: 4 columns at 1120), 280 (offer cards: 3), 180 (paper links: 5), 190 (stat cards: 5), 260 (address form: 2), 220 (record form: 3), 160 (tier averages: 3). Every grid falls to one column at 358 px. |
| Two columns | A flex-wrap row: main `flex: 999 1 600px; min-width: 0`, aside `flex: 1 1 300px` (rails, summaries; 340 for order summaries), gap 32. The aside drops under main on phones. The Account side nav comes first in the DOM, so it lands on top (as a row of chips under 900 px). Never sticky, except the solutions rail, whose card sticks 16 px from the top beside a long paper. |
| Hero | Flex-wrap row, gap 40: copy `flex: 1 1 460px`, `.stage` `flex: 1 1 420px`. Padding 48/72 px desktop, 24/40 phone. On phones the stage sits between the H1 and the numeral (HomePhone). |
| Real breakpoints | 900 px (`.nav-menu` folds behind `.nav-toggle`; the word "Cart" hides) and 768 px (`.buybar` shows below it). Everything else is intrinsic. |
| Type | Headings Poppins, body Hind Siliguri 17/1.7. Hero H1 `clamp(36px, 4.6vw, 54px)/1.08` 800 (34 px on phone); page H1 `clamp(30px, 4vw, 44px)/1.15` 800 (32 px on the login and register cards, 28 px on phone screens); H2 `clamp(26px, 3.2vw, 38px)/1.2` 800 (card titles 20–24 px); H3 17–21 px 700/1.3; lead 19 px; small 15 px; caption 14 px; labels 600 16/1.4. Bangla/Assamese text: no letter-spacing, no uppercase, line-height at least 1.7. `text-wrap: balance` on headings, `pretty` on paragraphs. |
| Numerals (`.numeral`) | Poppins 800, line-height 0.9. Hero "30": `clamp(88px, 10vw, 128px)`, `--gold` on night (navy when on paper). Bento "30": 112 px `--primary`. Stat cards 56 px, facts 26–28 px. Only true numbers (30, 10, 70/80, 3 hours). |
| `.q-rule` | The exam-paper divider that opens each section: `<div class="q-rule"><span>Q.1</span><span aria-hidden="true"></span><span>What's inside</span></div>`. Flex, gap 14, margin-bottom 16. Number Poppins 800 15 `--primary`, rule 1 px `--border` (flex 1), label Hind 600 15 `--muted-foreground`. Numbered down the page. |
| Icons | One inline stroke set: 24 viewBox, `stroke="currentColor"`, `stroke-width="1.75"`, round caps and joins, `fill="none"`, `aria-hidden="true"` (or `role="img"` + `aria-label` when alone). 20 px in buttons and lists, 22 px in alerts and the header, 24 px in feature cards. The 64 px 404 drawing keeps 1.75 by using a 64 viewBox. Set used: menu, bag, user, arrow-right, arrow-left, check, chevron-down, chevron-right, qr, truck, card, phone, mail, key, lock, download, trash, file, clock, package, pin, shield, alert, info, check-circle, x, plus, minus, tag, book, calendar, pencil, scan, chart, home, refresh. Keep them as one include set; no icon font, no emoji. |
| Brand | Favicon leaf on its navy rounded square (32 px) + "Exam" + "Leaf", Poppins 800 22. "Leaf" is `--leaf-light` #8FD694 on navy and `--accent` on paper. |
| Targets | Every link that is not inside a sentence, and every button, is at least 44 px tall (breadcrumb links, footer links, "Change", "Edit" included). |

## 1. Components (direction section 3, in its order)

### `.btn`
```html
<button class="btn btn-primary [btn-sm|btn-lg] [btn-block]" type="submit"><svg class="icon">…</svg><span>Save to my record</span></button>
<a class="btn btn-accent btn-lg" href="/shop/">Buy the books <svg class="icon">…</svg></a>
```
- Size: inline-flex, centred, gap 8. `min-height` 44 (`.btn`, `.btn-sm`), 52 (`.btn-lg`). Side padding 16 / 12 / 24. Radius 10. Poppins 700, 15 / 14 / 17 px, line-height 1.25. Icon 20 px, leading or trailing (a trailing arrow on "go" actions). `.btn-block` = width 100%.
- Colour on paper:
  - `.btn-primary`: `--primary` fill, white text, 2 px border of the same colour.
  - `.btn-secondary`: `--card` fill, `--primary` text, 1.5 px `--input` border.
  - `.btn-ghost`: transparent, `--primary` text.
  - `.btn-destructive`: `--destructive` fill, white text.
  - `.btn-accent`: `--accent` #1A6E30 fill, white text (6.3:1).
- Colour on `.band-night` (the tokens switch):
  - `.btn-accent`: #4CC265 fill, #07122B text (8.2:1).
  - `.btn-secondary`: transparent fill, white text, 1.5 px #A9B8D6 border.
  - `.btn-ghost`: white text.
- States:
  - Hover: fill to `--*-hover` (6 % darker). Secondary and ghost hover take `--secondary-hover`.
  - `:active`: `translate: 0 1px`.
  - `:focus-visible`: the ring.
  - `:disabled`: opacity .55, `cursor: not-allowed`.
  - `[aria-busy="true"]`: the label stays and a 16 px `.spinner` (2 px `currentColor` ring with one transparent side) shows before it. The button is also `disabled`. The spinner is the button's `::before` (no extra markup) and turns only inside the motion wrapper. Busy is for real waits only: the pay button until Razorpay's window has loaded and while the payment is checked (motion.md, g).
- Icon-only buttons (dismiss, close): 44×44, transparent, 22 px icon, `aria-label` required.
- Phone: the hero, checkout and login actions become `.btn-block`; button rows wrap with gap 12.

### `.field`
```html
<div class="field">
  <label for="pin">PIN code <span aria-hidden="true">*</span></label>
  <input class="input" id="pin" name="pin" inputmode="numeric" autocomplete="postal-code" required aria-describedby="pin-help">
  <p class="field-help" id="pin-help">6 digits, such as 781001.</p>
  <p class="field-error" id="pin-error"><svg class="icon">alert</svg><span>Enter the 6-digit PIN code.</span></p>
</div>
```
- Layout: column, gap 6. The label is Hind 600 16/1.4 `--foreground`. A required field gets a `--destructive` star (`aria-hidden`) plus `required` on the control. An optional field says " (optional)" in weight 400 `--muted-foreground` (the site's existing wording).
- `.field-help`: 14/1.6 `--muted-foreground`, under the control.
- `.field-error`: 15/1.5 weight 600 `--destructive` with an 18 px alert icon, under the control. Only rendered when there is an error.
- `[aria-invalid="true"]`: the control border becomes 2 px `--destructive` and `aria-describedby` points to the error id.
- After a failed submit, an `.alert.alert-error` with `role="alert"` sits at the top of the form. It lists each problem as a link to its field (Register artboard).
- Phone: every field goes full width (the form grids fall to one column).

### `.input` `.select` `.textarea` `.checkbox` `.radio` `.switch` `.otp`
- `.input`:
  - Box: height 48, padding 0 14, 1.5 px `--input` border, radius 12, `--card` fill, Hind 16. 16 px stops iOS zooming in.
  - `type` / `inputmode` / `autocomplete` on every field (`tel` + `tel-national`; `numeric` + `postal-code`; `email`; `name`; `new-password`; `bday`).
  - Placeholders only as examples ("e.g. 52.5"), never instead of a label.
- Prefixed input (+91): the 1.5 px border and radius move to a wrapper. Inside, a prefix cell (`--muted` fill, 1 px `--border` on its right, 600 weight, `aria-hidden`) and a borderless input that fills the rest.
- `.select`: the same box with `appearance: none` and padding-right 44. A 20 px chevron-down sits at right 14, top 14, with `pointer-events: none`.
- `.textarea`: min-height 96, padding 12 14, line-height 1.7, `resize: vertical`, `rows="2"` for "What to revise".
- `.checkbox`, `.radio`: native, 22×22, `accent-color: var(--primary)`. Each sits inside its `<label>` row: flex, gap 12, min-height 44, text 16/1.6. The consent checkbox carries the full sentence as its label text.
- Selectable card (`label.card` holding an `input.radio`): used for saved addresses, payment methods and the product option.
  - Unchecked: 1 px `--border`, padding 16.
  - `:has(input:checked)`: 2 px `--primary` border, padding 15, so nothing shifts.
  - `:has(input:focus-visible)`: the ring.
  - Content: title Poppins 700 16, sub-line 15/1.6 muted, optional badge.
- `.switch`: `<input class="switch" type="checkbox" role="switch">` with `appearance: none`, 48×28, radius 999.
  - Track: `--input` when off, `--accent` when on.
  - Knob: a 20 px white circle drawn as `radial-gradient(circle at 14px 14px, #fff 10px, transparent 10.5px)`. It sits at 14 px off and 34 px on.
  - Row: label text on the left, switch on the right, min-height 44.
- `.otp`: `<div class="otp" role="group" aria-label="6-digit code">` holding six `<input class="input" inputmode="numeric" maxlength="1" aria-label="Digit n of 6">`.
  - Boxes: 48×56, gap 8 (328 px in all, fits a 358 px column), Poppins 700 24, centred. The first box has `autocomplete="one-time-code"`. Focus shows the ring.
  - It needs about 20 lines of static JS: auto-advance, Backspace to the previous box, a 6-digit paste fills all six, and the boxes join into one hidden `code` field.
  - Without JS, render a single `.input` with `inputmode="numeric" autocomplete="one-time-code" maxlength="6"`.
- Quantity stepper (Product, Cart): a 48 px box (1.5 px `--input`, radius 12) holding − and + `.btn-ghost` buttons (44×44, `aria-label` "One copy fewer/more") around a 44 px number input (Poppins 700 17, centred). It works as a plain number input without JS.

### `.card` → `.card-header` `.card-body` `.card-footer`
```html
<div class="card"><div class="card-header"><h2>Summary</h2><p>…</p></div><div class="card-body">…</div><div class="card-footer">…</div></div>
```
- Box: `--card`, 1 px `--border`, radius 12, `--shadow-card`, flex column.
- Header: padding 20 20 0, gap 4. Title Poppins 700/800, 19–24 px. Optional description 15–16 `--muted-foreground`.
- Body: padding 20, gap 12. Footer: padding 16 20, 1 px `--border` top rule, flex-wrap, gap 12.
- Dense cards (paper links): padding 16. Feature cards (bento): a 44 px rounded `--secondary` square with a 24 px `--accent` icon, then an H3 19 px and muted text.
- `.card-interactive`: the whole card is the `<a>`. Hover (`hover: hover`) gives `translate: 0 -2px`, focus gives the ring, and the shadow never changes. Product cards hold cover, chips, a 17 px title and the price at the bottom (`margin-top: auto`). Paper links show "E-01" (Poppins 800 22), a trailing arrow and "70 marks · 3 hours".
- Phone: same, full width.

### `.badge`
- Shape: inline-flex, height 24, padding 0 10, radius 999, Poppins 700 12, gap 4, optional 14 px icon, `white-space: nowrap`.
- Variants:
  - `.badge-easy`: #1B7F3B fill, white text.
  - `.badge-medium`: #1A5FB4 fill, white text.
  - `.badge-hard`: #A0272D fill, white text.
  - `.badge-gold`: `--gold` fill, `--foreground` text ("Best value").
  - `.badge-muted`: `--muted` fill, `--muted-foreground` text (kinds, statuses: "Paid", "Used by default", "Confirmed", "WELCOME10 applied").
- Subject chips (an extension of the same rule): `.badge-physics` / `-chemistry` / `-maths` / `-biology` use the subject base fill and white text. On a navy surface (`.qr-card`) the chip flips to the pill colour fill with base-colour text.
- As a link ("The other books" on the Book page), a chip grows to min-height 44, padding 0 16, 15 px, with a trailing arrow.
- Tier and status meaning is always in the words, never in the colour alone.

### `.alert` + `.alert-info` `.alert-success` `.alert-warning` `.alert-error`
```html
<div class="alert alert-info" role="status"><svg class="icon">info</svg><div><p class="alert-title">Cash on delivery</p><p>For accounts with …</p>[links or a small form]</div></div>
```
- Layout: flex, gap 12, padding 16, radius 12, 1 px border, no side bar. Icon 22 px. Title Poppins 700 16/1.4; text 16/1.7 `--foreground`; the content column has gap 6.
- Variant colours (tint / border / icon):
  - info: `--info-bg` / `--info-line` / `--info-fg`.
  - success: `--success-*`. Icon check-circle.
  - warning: `--warning-*`. Icon alert.
  - error: `--error-*`. Icon alert.
- `role`: `role="status"` for messages that appear after an action. `role="alert"` for the error summary only.
- Drawn uses:
  - Info: the cash-on-delivery rule (Checkout) and "Keep your marks" with Register/Log in links (Book).
  - Success: "Payment received" (Order status).
  - Warning: deletion is final after seven days (Account).
  - Error: the form error summary (Register).
- Phone: full width; links in the alert wrap.

### `.toast` region (Django messages)
```html
<main id="main" tabindex="-1"><ul class="toast" aria-label="Messages"><li><details class="toast-item success" open><summary class="btn btn-ghost btn-icon" aria-label="Dismiss">x</summary><svg class="icon">check-circle</svg><p>ExamLeaf Chemistry Sample Papers 2027 is in your cart.</p></details></li></ul>
<p id="announce" class="sr-only" role="status"></p> …</main>
```
- Region: fixed under the header at the top right (top 80 = header + 16, right = the gutter), width `min(400px, 100% - 32px)`, gap 8, `z-index` 40.
- Each message: `--card`, 1 px `--border`, radius 12, `--shadow-card`, padding 12 4 12 16. A 22 px icon in the alert colour of its tag (`message.tags` gives success/info/warning/error), text 16/1.6, and a 44 px dismiss button.
- No auto-dismiss: it stays until dismissed or the next page. Dismiss closes its `<details>` (works without JavaScript); with site.js it leaves with the exit animation first, and Escape dismisses every toast.
- Screen readers: text present at load is not announced, so site.js copies the messages once into `#announce` (a polite `role="status"` region on every page, inside `<main>`).
- Phone: the region moves to the bottom (left/right 16, bottom 16); it enters from below.

### `dialog.dialog`
```html
<dialog class="dialog" aria-labelledby="rm-title">
  <div class="card-header"><h2 id="rm-title">Remove this book?</h2><button class="btn btn-ghost btn-sm" aria-label="Close">x</button></div>
  <div class="card-body"><p><strong>ExamLeaf Chemistry Sample Papers 2027</strong> leaves your cart. You can add it again from the shop.</p></div>
  <div class="card-footer"><button class="btn btn-secondary">Keep it</button><button class="btn btn-destructive">Remove</button></div>
</dialog>
```
- Box: width `min(32rem, 100% - 32px)`, padding 0, no border, radius 12, `--card`, `--shadow-dialog`. `::backdrop` is `--backdrop`. Header padding 20 12 0 24, title Poppins 800 22. Body padding 8 24 0. Footer right-aligned, gap 12, padding 24, no rule.
- Behaviour:
  - Opened with `showModal()` by one delegated `[data-dialog]` click handler in a static JS file (R15).
  - Esc and Close dismiss it.
  - Without JS, the Remove/Cancel button simply submits its form.
  - Only for removing a cart line and cancelling an order.
- Drawn on Cart: press Remove in Play mode.
- Phone: the same box with 16 px margins; footer buttons wrap.

### `.tabs` (radio-based)
```html
<fieldset class="tabs"><legend class="sr-only">Subject</legend><div>
  <label><input type="radio" name="subject" value="all" checked> All subjects</label><label><input type="radio" name="subject" value="physics"> Physics</label> …
</div></fieldset>
```
- Inner row: flex, gap 4, 1 px `--border` bottom rule, `overflow-x: auto` (a phone scrolls it; it never wraps).
- Label: min-height 48, padding 0 16, Poppins 700 15, `--muted-foreground`. The radio is visually hidden but focusable.
- Checked label: `--primary` text and a 3 px underline as `box-shadow: inset 0 -3px 0 var(--primary)`. `:has(input:focus-visible)` gives the ring.
- Filtering in CSS, for example `.catalogue:has(input[value=physics]:checked) .card[data-subject]:not([data-subject=physics]) { display: none }`. Browsers without `:has` show everything.

### `details.accordion`
```html
<details class="accordion" name="faq" open><summary>Are the solutions really free? <svg class="icon">chevron-down</svg></summary><div>…</div></details>
```
- Summary: flex space-between, gap 16, min-height 56, padding 6 0, `list-style: none` (and the `::-webkit-details-marker` hidden), Poppins 700 17 `--primary` (16 in compact places). Chevron 22.
- Open state: the chevron turns 180° (a state, outside the motion wrapper; only the transition is inside). Content padding-bottom 20, gap 12.
- Items share 1 px `--border` rules: one on top of the group, one under each item. FAQ items share `name="faq"`, so one opens at a time.
- Uses: Home FAQ, Solutions "Instructions and allotment of marks", the phone checkout's "Order summary · ₹718.20".

### `.skeleton`
`<span class="skeleton" aria-hidden="true">`: a block, radius 6, `--border` fill, lines 10–14 px tall. Its width is set where it sits. It is still: no pulse and no shimmer, because the page does not refresh itself (motion.md). The slot keeps its final size; images reserve theirs with `aspect-ratio: 480/678` and a subject base fill. Drawn as the invoice slot on Order status, next to "The invoice will appear here in a few minutes."

### `.table-wrap > table.table`
- `.table-wrap`: `overflow-x: auto`, 1 px `--border`, radius 12, `--card`.
- `table.table`:
  - Whole table: width 100%, `border-collapse: collapse`, 16/1.6.
  - `<caption class="sr-only">`.
  - `th` (scope col): sticky top 0, `--secondary` fill, Hind 600 15, padding 10 14, 1 px bottom rule, nowrap.
  - `td`: padding 12 14, 1 px top rule between rows, `vertical-align: top`.
  - Numeric columns: right-aligned, `tabular-nums`, nowrap.
  - `tfoot` (Total): a 2 px `--foreground` top rule, Poppins 700.
- Wide tables get a `min-width` so phones scroll them instead of squashing them: 560 for the cart, 640 for the record.
- Solution step tables are two columns, Step | Marks, with a Total row.

### `.breadcrumb`, `.pagination`
- `.breadcrumb`: `<nav class="breadcrumb" aria-label="Breadcrumb"><ol>…</ol></nav>`. 15 px, flex-wrap, gap 4. Links are 600, underlined `--primary`, min-height 44. Separators are a 16 px chevron-right in `--muted-foreground` (`aria-hidden`). The current page is `<span aria-current="page">` in muted.
- `.pagination`: `<nav class="pagination" aria-label="Pages"><ul>…</ul></nav>`. Items are at least 44×44, padding 0 12, radius 10, Poppins 700 15, gap 8.
  - Links: 1.5 px `--input` border, `--primary` text.
  - Current page: `aria-current="page"`, `--primary` fill, white text.
  - Disabled Previous/Next: a `<span aria-disabled="true">` in muted.

### `.stepper` → `.step` `.step-done` `.step-current`
```html
<ol class="stepper" aria-label="Checkout"><li class="step step-done"><a href="…"><svg class="icon">check</svg> 1. Address</a></li><li class="step step-current"><span aria-current="step">2. Delivery</span></li><li class="step">3. Payment</li><li class="step">4. Done</li></ol>
```
- Layout: flex, gap 8. Each `.step` is `flex: 1`, padding-top 4, a 4 px top border, Poppins 15, label min-height 44.
- `.step-done`: `--primary` border, weight 600, a link back with an 18 px check icon in `--accent`.
- `.step-current`: `--primary` border, weight 700, `--primary` text.
- Upcoming steps: `--border` border, weight 600, muted text.
- Steps: Address → Delivery → Payment → Done.
- Phone (CheckoutPhone): only the current step keeps its words. The others show their number, with the label kept in `.sr-only`; done steps keep the link on the number.

### `.tile` + `.tile-physics` `.tile-chemistry` `.tile-maths` `.tile-biology`
```html
<a class="tile tile-physics" href="/books/physics-2027/">
  <span class="pill">30 papers</span><span class="tile-name">Physics</span>
  <span class="tile-meta">10 Easy · 10 Medium · 10 Hard<br>70 marks · 3 hours</span>
  <span class="tile-go">Open the papers <svg class="icon">arrow-right</svg></span><img src="…" alt="" width="480" height="678">
</a>
```
- Box: flex column, gap 8, min-height 300, padding 20, 2 px `--foreground` border, radius 12, subject base fill, white text, `--shadow-hard`, `overflow: hidden`, `view-transition-name: book-<subject>`.
- Children:
  - Pill: 24 tall, padding 0 10, pill-colour fill, base-colour text, Poppins 700 12.
  - Name: Poppins 800 28/1.15.
  - Meta: Hind 600 15/1.5 in the pill colour (7.6–9.1:1).
  - "Open the papers": 600 16 with a 20 px arrow that wraps with the last word, at the bottom (`margin-top: auto`), max-width 58 %.
  - Cover: 112 px wide, absolute at right −14 / bottom −34, rotated 8°, `--shadow-cover`, `alt=""`.
- Sticker press: `:active` moves the tile 3 px right and down and drops the hard shadow; the move takes 120 ms in the motion wrapper. Focus gives the ring. No hover tilt.
- Phone: the Home page puts the four tiles in a scroll-snap strip: `grid-auto-flow: column; grid-auto-columns: 80%; overflow-x: auto; scroll-snap-type: x mandatory`. The strip bleeds to the screen edges and the next tile peeks in. Elsewhere (404) the grid falls to one column.

### `.band` `.band-night`
- Full-bleed `<section class="band band-night">`. The tokens invert:
  - Fill `--night`, white text, muted text #A9B8D6.
  - Accent #4CC265 with #07122B on top.
  - Numerals and seals in `--gold`.
  - Hairlines `--night-line`, focus ring #8FD694.
- The header is the navy start of the band (`--primary`, see `.nav`).
- Hero background: the static spotlight and the melt, no blur and no animation:
  - Desktop: `radial-gradient(52% 60% at 76% 50%, rgba(76,194,101,.30), transparent 70%), linear-gradient(180deg, #0B2A5B 0, #07122B 260px)`.
  - Phone: the spot moves to `70% 34% at 50% 44%`, behind the stage, and the melt ends at 200 px.
- Final call-to-action band: the section rhythm, H2 + muted line on the left, accent and ghost buttons on the right (wrapping). A 1 px `--night-line` separates it from the footer.

### `.stage`
- Box: `<div class="stage">` holding four `<img class="stage-cover" width="480" height="678" alt="Physics Sample Papers 2027, cover">`, in Physics, Chemistry, Mathematics, Biology order. Flex, centred, padding 16 0 40.
- Each cover:
  - Width `min(30vw, 172px)`; on phone 104 px.
  - Every cover after the first: margin-left `max(-56px, -10vw)` (−34 px on phone).
  - `transform`: rotate −8°, −3°, 3°, 8°; the outer two also `translateY(14px)`.
  - z-index 1, 2, 3, 2.
  - Radius 6, `--shadow-cover`, and the spine highlight `::after` from R1.
- One cover lifts: under `hover: hover` and the motion wrapper, `.stage-cover:hover { translate: 0 -14px }`. Use the `translate` property so the rotation stays.
- Nothing animates on load. The first cover gets `fetchpriority="high"`, the others `loading="lazy"`.
- Serve `<picture>` with AVIF, then WebP, then PNG, at 240/320/480w.

### `.marker`
- Static (drawn): `<mark class="marker">the solutions free</mark>`. The fill is a highlighter stroke made with a hard-stop gradient, `linear-gradient(180deg, transparent 50%, #FFE27A 50% 92%, transparent 92%)`, with padding 0 2px and the colour inherited (ink or navy, never on night). One per view, three words or fewer, one line.
- Drawn on entry: add `data-draw`. Inside the motion wrapper and `@supports (animation-timeline: view())`, a `::after` scales 0 → 1 from the left (tokens.css).
- Home draws its one marker (Q.1) on entry; it never wraps (`white-space: nowrap`), so the stroke stays on one line.

### `.price` → `.price-now` `.price-mrp` `.price-save`
```html
<p class="price"><span class="price-now">₹499</span><s class="price-mrp"><span class="sr-only">MRP </span>₹548</s><span class="price-save">Save ₹49 (9%)</span></p>
```
- Layout: flex-wrap, baseline, gap 2 10, `tabular-nums`.
- `.price-now`: Poppins 800 `--foreground`; 22 on product cards, 30 on offer cards, 36 on the product page.
- `.price-mrp`: 16, muted, struck through, only when the MRP differs.
- `.price-save`: 600 15 `--accent`, always in words.
- Display prices drop zero paise ("₹299"). Totals keep paise ("₹718.20", "−₹79.80").
- Inside a `<label>`, use `<span class="price">`.

### `.empty`
- Box: `<div class="empty">`, a 2 px dashed `--border`, radius 12, `--card`, padding 48 24. Centred column, gap 14, `text-wrap: balance`.
- Contents, in order:
  - A 64 px inline drawing (stroke 1.75, `--primary`).
  - An optional eyebrow ("Error 404").
  - The title: H1 on the 404, H2 elsewhere.
  - Text in muted, max 34rem.
  - ONE button, plus an optional text link ("or open the shop").
- Uses: 404, an empty cart ("Your cart is empty." + See the books), an order lookup miss.

### `.timeline` → `.timeline-item` (`.done` `.current`)
```html
<ol class="timeline"><li class="timeline-item done"><span class="dot"><svg class="icon">check</svg></span><span><strong>Ordered</strong><time datetime="…">8 Oct 2026, 10:42</time></span></li> …</ol>
```
- Each item: a grid, `28px 1fr`, column-gap 16. The left column holds a 28 px dot and a 2 px connector below it (flex 1, min-height 28, gap 4). The text column has padding-bottom 20, except on the last item.
- Dots and connectors:
  - `.done`: `--primary` dot with a white 16 px check; the connector below is `--primary`.
  - `.current`: a 3 px `--accent` ring around a 10 px `--accent` centre, with `aria-current="step"`.
  - Upcoming: a 2 px dashed `--input` ring on white; the label is muted 600.
  - Connectors elsewhere are `--border`.
- Text: label Poppins 700 17 (line-height 28); time or note 15 muted.
- Content: the real events come from `Order.timeline()`. After them come the remaining statuses in order (Packed, Shipped, Delivered) as upcoming items; Shipped carries "We email you the tracking number."

### `.qr-card`
- Box: the QR landing header on every paper page (`/s/<code>/`, the URL the printed QR opens). A `--primary` card, radius 12, padding 28 32 (20 on phone), `--shadow-card`, white text. Flex-wrap, gap 20 32.
- Content column (`flex: 999 1 420px`):
  - A chip row, gap 8: the subject chip (pill fill, base text), the tier badge, and the code chip ("PHY-M04": 1 px `rgba(169,184,214,.5)` outline, #A9B8D6 text).
  - Eyebrow: 600 16 #A9B8D6, "Sample Paper M-04 · Medium · ASSEB Class 12".
  - Title: Poppins 800 `clamp(30px, 3.6vw, 40px)` (28 on phone), white, "Physics: solutions". It is the H1 on the paper page and a `<p>` in the Home preview.
  - `<dl>`, gap 8 32: `dt` 14 #A9B8D6; `dd` Poppins 800 26 (22 on phone) in `--gold`. Full marks, Pass marks, Time.
- Seal (`.seal`), right-aligned (it wraps under the content on narrow cards):
  - 104 px circle (88 on phone), 2 px `--gold` border, an inner 1 px dashed gold ring (`outline-offset: -8px`).
  - A 24 px scan icon and "Scan verified", Poppins 800 12/1.15, in gold, rotated −8°. Gold on navy is 8.3:1.

### `.nav` `.nav-toggle` `.nav-menu`
```html
<header class="nav"><div class="container">
  <a class="brand" href="/">[mark] Exam<span>Leaf</span></a>
  <a class="cart" href="/shop/cart/" aria-label="Cart, 2 books">[bag] <span class="cart-label">Cart</span> <span class="count">2</span></a>
  <nav class="nav-menu" id="site-menu" aria-label="Main">Shop · Log in · <a class="btn btn-accent btn-sm">Register</a></nav>
  <button class="nav-toggle" aria-expanded="false" aria-controls="site-menu">[menu] Menu</button>
</div></header>
```
- Header: `--primary` fill, white text, 1 px `--header-line` bottom. The container is flex, min-height 64, gap 8.
- Brand: min-height 44, `margin-right: auto`.
- Links: Hind 600 16, min-height 44, padding 0 12, radius 8. The current page has `aria-current="page"` and a 3 px #8FD694 inset underline.
- Register: the night `.btn-accent.btn-sm` (#4CC265 with #07122B text), margin-left 8.
- Cart (only when the cart has items): a 22 px bag, the word "Cart", and the count pill (22 tall, `--gold` fill, `--night` text, Poppins 700 12).
- Logged in, the menu reads: Shop · My record · Account · Log out. Log out is a POST form whose button is styled like the links.
- Under 900 px:
  - `.nav-menu` hides and `.nav-toggle` shows: a 22 px menu icon + "Menu", Poppins 700 15, 1.5 px `--header-line` border, radius 10, min-height 44.
  - The cart stays visible. The word "Cart" hides, but the count and the `aria-label` stay.
  - Toggling opens the menu as a full-width panel under the header: `--primary` fill, links 48 tall at 17 px with chevrons and `--header-line` hairlines, Register as a `.btn-lg.btn-block`, one shadow `0 16px 24px rgba(7,18,43,.35)`.
  - `aria-expanded` follows the state. Without JS, keep today's checkbox toggle.

### `.footer`
- Box: `<footer class="footer band band-night">`, padding 56 0 32. The container is a column with gap 40.
- Top row (flex-wrap, gap 32):
  - The brand column (`flex: 2 1 300px`): wordmark, then one line, "Sample papers for the Assam Board (ASSEB) Class 12 examination, with free worked solutions behind a QR code." (16/1.7 #A9B8D6, max 22rem).
  - Three link columns (`flex: 1 1 160px`): Books, Shop, ExamLeaf. Each has an H2 (Poppins 700 15 #A9B8D6) and links in white, 16 px, min-height 44.
- Bottom row: a 1 px `--night-line` top rule, padding-top 20, 15 px #A9B8D6, space-between. It reads "© ExamLeaf LLP" and "Payments through Razorpay: UPI, cards, net banking".
- Phone: the columns wrap: brand full width, then the link columns two by two.

## 2. Drawn patterns that sit beside the vocabulary
- `.no-cover` (the existing `shop/no_cover.html`): for books without a cover image (the Solutions books today).
  - Box: `aspect-ratio: 480/678`, radius 6, subject base fill, padding 16, `--shadow-cover`, `aria-hidden`.
  - Inside: "Exam" + "Leaf" (Poppins 800 15), the subject name (Poppins 800 24), a kind pill ("Solutions", pill colour), and "Class 12 · 2027" (600 14, pill colour).
- `.buybar` (R7) was drawn but no page uses it; its rules were removed in the craft pass. Bring them back with the first page that needs a bar fixed to the bottom of a phone (and `scroll-padding-bottom` with it).
- Solutions page parts (the existing `solutions.html` class names):
  - `.group`: H2 grid `48px 1fr auto`, Poppins 700 18, with a 2 px `--primary` bottom rule. The marks ("2×10 = 20") are Hind 600 16, nowrap, in the right margin.
  - `article.question`: grid `48px minmax(0,1fr) auto`, gap 0 12, padding 24 0, 1 px bottom rule. `.qno` is Poppins 800 17 `--primary` (empty on an "Or" alternative), `.qtext` is 17/1.7, and `.marks` "[2]" is 600 16 muted in the right margin. `.options` is an unbulleted list of "(i) …".
  - `.solution`: spans columns 2 to the end (the full width on phone), a `--card` box with a 1 px `--border`, radius 12, padding 16, gap 12. Its label is "Solution": Poppins 700 14 `--accent` with an 18 px check-circle. It holds the answer line ("Ans. (iv) … (1)"), a step table, a "Final answer:" line (`--secondary` fill, radius 10, padding 10 14), and a "Diagram expected:" box (2 px dashed `--input`, radius 10, a 22 px chart icon, the sentence).
  - Maths is KaTeX on the site; the canvas sets it as text, with italic variables, × and superscripts.
  - `.or`: a 1 px rule, "Or" in Poppins 800 15 `--primary`, a 1 px rule.
  - Below the questions, a "Record your marks" `.card` (`id="record"`): Date, Marks obtained (out of 70), Time taken (minutes), What to revise, then "Save to my record".
  - Desktop has a right rail, "On this paper", with jump links to Q.1–Q.4 and Record.

## 3. Pages (artboard → template)
- Home (`home.html`), top to bottom:
  - Hero band.
  - Q.1 What's inside: a bento of one big card (`flex: 1 1 400px`), a 2×2 grid of feature cards, and a full-width trust strip.
  - Q.2 subject tiles.
  - Q.3 How it works: four numbered steps beside the qr-card and a real step-table excerpt.
  - Q.4 The books: three offer cards and "Go to the shop".
  - FAQ, the final band, the footer.
- Book (`book.html`):
  - Breadcrumb.
  - Cover (260 px, `view-transition-name: book-physics`) beside chips, H1, edition line, three facts (30 / 70 / 3 hours), "Buy this book · ₹299" and "Solutions book · ₹249", and the info alert.
  - Three tier blocks: a q-rule "E-01 to E-10", tier badge + H2, then 10 paper links.
  - Links to the other books.
- Solutions (`solutions.html`): the qr-card, "Record your marks" + "All 30 Physics papers", the instructions accordion, the questions by group, the record card, the rail. Logged-in header.
- Catalogue (`shop/catalogue.html`):
  - H1 and lead, a trust row, subject `.tabs`.
  - The featured bundle card: two covers fanned, Best value / Bundle / Physics chips, price with MRP and saving, "Add to cart", "See the bundle".
  - Eight product cards (four Sample Papers, then four Solutions), the "Find your order" line.
- Product (`shop/product.html`):
  - Cover 400 px beside the buy column: chips, H1, price, the description, "Choose" (product / bundle radio cards), Copies + "Add to cart", and three trust lines.
  - What's inside: five stat cards.
  - Details: a `<dl>` beside the Solutions-book upsell card.
- Cart (`shop/cart.html`): the toast, the lines table with thumbnails, a stepper and Remove (opens the dialog), "Update copies", and the summary card. The summary card lists Books, Coupon and Shipping, then "Total before shipping", the applied coupon chip, Checkout (block), "Add more books" and the guest line.
- Checkout (`shop/checkout.html`, plus the Pay step): one page on desktop.
  - The stepper, then three numbered step cards.
  - 1 Address: two saved addresses and "A new address" with its form and the save switch.
  - 2 Delivery: the rate for the state.
  - 3 Payment: online or cash-on-delivery cards, the COD alert, "Pay ₹718.20" (opens Razorpay) and the Razorpay line.
  - The order summary sits on the right.
- CheckoutPhone: the same steps as separate screens. The Payment screen shows the done steps as "Change" rows, the payment cards, the COD alert, the order-summary accordion and the `.buybar`.
- Order status (`shop/order_detail.html`, via the email token link): eyebrow, "Your order is paid" + status chip, the success alert. "Where it is" holds the timeline and "Cancel the order" with the refund line. Then the private-link note with a lock icon, and the summary card (delivery address, payment line, invoice skeleton).
- Log in (allauth `login.html`), a card on `--secondary`, in this order:
  - Mobile number (+91) with help, then the code: label, "New code in 0:30", `.otp`, "Sent to … Send a new code".
  - Log in (primary, block), "or".
  - Email me a code, Continue with Google, Use a passkey.
  - Last, "Log in with email and password".
  - A "Why log in" list sits beside the card.
- Register (allauth `signup.html`): the error summary, then numbered fieldsets.
  - 1 About you: name, email, mobile (optional), password ×2.
  - 2 Your class: class, board, district (optional), date of birth.
  - 3 Because you are under 18: a `--secondary` fieldset with the parent's name and the parent's email.
  - The consent checkbox with the exact sentence from `SignupForm`, then Register. A "What we keep" card sits beside it.
- Account (`my_account.html` + `record.html`): a side nav, then cards.
  - My record: tier averages, Subject/Tier filters, the attempts table, pagination.
  - My orders.
  - Details and addresses, with the teacher-access line.
  - Parent's consent (confirmed state).
  - Your data: the warning alert, "Download my data", "Delete my account".
- 404 (`404.html`): the `.empty` block, then the four subject tiles under "Open a book".
- Email (`shop/email/confirmation`, HTML part): 600 px tables with inline styles only.
  - A navy header row with the wordmark.
  - Thank-you H1 and the paid line.
  - The items table with a 2 px rule above the Total.
  - Delivery address, then the "Open your order" button (a table cell filled #1A6E30), then the private-link line.
  - Tracking and cancel lines, the sign-off, and a `--secondary` footer.
  - Fonts fall back to Segoe UI / Helvetica / Arial.

## 4. Motion: docs/design/motion.md
- The timing scale (0 / 150 / 220 / 360 ms), the easings, the sequencing and interruption rules and the seven signature interactions are in `motion.md`; the tokens and the wrapper are at the top of site.css.
- At most two effects per view. Home: the cover lift and the sticker press (the marker draws further down). Book and Catalogue: the card lift and the view transition.
- View transitions pair across pages: the Home tile and the Book cover share `book-<subject>`; a product card's cover and the Product page cover share `cover-<product id>` (a `style` attribute: two products of one subject sit on the catalogue). Each name is unique on its page. The page cross-fades over 360 ms; none after a form is sent.
- Nothing hides the LCP element, and nothing animates width, height, position, shadow or blur. Press feedback (`translate` on `:active`) and the chevron state work with reduced motion too.

## 4a. Craft pass (2026-10-08): what the built site does beyond the drawings
- Stylesheets: `site.css` (every page, about 51 KB), then `home.css` (home.html), `shop.css` (templates/shop/base_shop.html) or `account.css` (templates/base_account.html, allauth/layouts/base.html) with the rules only those pages use, so no page loads 60 KB of CSS (content/test_craft.py checks it); each is render-blocking, as the CSP allows no `onload` swap. `print.css` (`media="print"`, solutions page) and `staff.css` (clip preview) load only there. site.css is written one rule per line without optional spaces; the explanations live in these docs.
- Tokens added to site.css (copied to tokens.css on 8 October 2026): `--t-instant` `--t-fast` `--t-base` `--t-slow`, `--ease-enter` `--ease-exit` (motion.md); the type scale `--fs-display` `--fs-h1` `--fs-h1-card` `--fs-h2` `--fs-title` `--fs-card` `--fs-h3` `--fs-h4` `--fs-lead` `--fs-body` `--fs-small` `--fs-caption`; `--measure: 66ch`. The unused whole-site `[data-theme="dark"]` block was removed: dark stays on the bands.
- Type: card titles are `--fs-card` (22) everywhere, section sub-heads `--fs-title`; reading columns (solutions, legal pages, About, FAQ) are at most `--measure`; `p, li, dd, figcaption` wrap `pretty`, h1–h4 `balance`; Hind Siliguri sits in the heading stack so Assamese names and titles get its Bengali glyphs; `:lang(as)`/`:lang(bn)` text gets line-height 1.8 (headings 1.45), no tracking, no uppercase. Tables ask for `tabular-nums`, but no font of the site has tabular figures: Poppins 4.004 and Hind Siliguri 1.001 (google/fonts, the originals of the subsets) have proportional digits and no `tnum` feature, so a re-subset with `--layout-features+=tnum` gives byte-identical files (checked 8 October 2026). Aligned digits need another family for the `.num` cells, a design decision (coverage-matrix.md, Open journeys).
- Empty states draw one of `templates/_empty_art.html` (`sheet`, `cart`, `orders`, `attempts`, `results`, and the 404's `missing`): 64 viewBox, 1.75 stroke, one marker-yellow highlight; only pages that show an empty state carry the drawing. Inside a card (My account) the empty state is a compact row.
- Forms: `_required_note.html` explains the red star once at the top of the longer forms; `_field.html` points `aria-describedby` at the error even without help text; the marks forms use `_field.html` too. Controls: hover darkens the border, `:user-invalid` turns it red when the student leaves a wrong field, `:disabled` is grey.
- Keyboard: the menu checkbox is in the tab order only under 900 px; Enter works the menu and the subject tabs as Space does; Escape closes the menu (focus back on Menu) or dismisses the toasts. Dialogs open on their safe button (`autofocus` on "Keep it" / "Keep the order"). The skip link lands on `<main tabindex="-1">`.
- Home: each stage cover is the link to its book (hover, focus and tap lift it and light its spine); the bento's big card ends with the three tiers (E-01 to E-10 …) instead of repeated chips.
- Solutions: the question text and the solution's paragraphs keep `--measure`; the rail's card is sticky beside the paper; each question is `content-visibility: auto`; KaTeX draws a question as it nears the screen (static/js/math.js) and its stylesheet is applied at the end of the page; printing gives the paper header, the instructions, every question with its marks and solution, a new page per question group.
- Account: on phones the side nav is a row of chips; the tier averages show once a mark is saved.
- Pay: the pay button is busy until Razorpay's window has loaded.
- Cart on phones (under 600 px): each line stacks (book, then copies and amount) instead of a table scrolled sideways; the copies buttons keep their place while hidden, so nothing shifts when site.js shows them.
- Header at 320 px: Menu shows its icon only (the checkbox keeps the name; `aria-expanded` follows it) and the wordmark steps down to 20 px.
- allauth's passkey scripts load with `defer` (templates/mfa/webauthn/snippets/scripts.html).

## 5. Canvas-only levers
The artboards have three Tweaks: accent colour (#1A6E30 / #1A5FB4 / #8A6508), dark bands on/off, and density (comfortable 96/24 vs compact 64/16). They are for comparing options. The built site uses the defaults above: leaf accent, night bands, comfortable density.

## 5. As built (2026-10-08, canvas pass against the Next.js frontend)
The canvas now draws every page of the built product (71 artboards, rows Public to Errors and offline). Where the final anatomy differs from the sections above:
- `.seal` reads "ExamLeaf · Official solutions", not "Scan verified".
- Cart lines are a list, not a table: 56 px cover, title link, "₹… each", a ghost Remove (opens the dialog), the copies stepper (each step saves: no "Update copies"), the line total. The summary card holds Books, the savings ("Coupon WELCOME10"), Shipping "at checkout, from your state", Total before shipping, then the coupon form (Coupon code + Apply) or the gold "WELCOME10 applied" badge with Remove coupon, Checkout, Add more books and, for a guest, the log-in line.
- Checkout's three numbered cards only choose: the button is "Continue to payment" (or "Place the order: pay ₹… on delivery") and leads to a separate "Review and pay" page (stepper at 3, the done steps link back) whose Payment card holds "Pay ₹…" and its states (test mode, window not loaded, service down, refused, busy). A guest gets Email address and the address form, online payment only.
- The order pages (Done, the emailed link, the account's order) share one anatomy: eyebrow "Order …", H1, status badge, "Where it is" (timeline, then Cancel the order and the refund line), "Your papers", the summary card with the invoice or its skeleton and "Contact us with the order number". The success alert shows on Done only; the link page adds the lock note.
- Log in: Mobile number (+91) and "Text me a code" first, then "or", Email me a code, Continue with Google, Use a passkey, and "Log in with email and password" in a details. The six boxes are a second step on the same card ("No code? Send a new code"); there is no countdown.
- Register has no mobile number: "1 About you" (full name, email, password twice), "2 Your class" (class, board, district, date of birth), "3 Because you are under 18" on the secondary fill, the consent checkbox, then Register with "We email you a code to confirm your address."
- Account: separate pages beside one navigation (My account, My record, Learning, My orders, Details, Addresses, Log-in and security, Consent and your data, Teacher access, Revision course), a column on desktop and a scrolling row of chips under 900 px; an empty state inside a card is the compact dashed row.
- Book page: no "The other books" chips; a "Try Paper E-01 first" line, and the E-01 card says "Open to everyone". Solutions rail: "Questions from 1(a)" … and "Record your marks". 404: "See the books", tiles without the marks line.
