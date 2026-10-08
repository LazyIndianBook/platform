# ExamLeaf motion language (decided 2026-10-08)

Motion on ExamLeaf confirms what the reader just did, or shows that something moved from one place to another. It never decorates. Students read solutions for an hour at a time on cheap phones, so the reading surfaces stay still and everything here is cheap to run: `transform` and `opacity` only, no JavaScript animation library, no layout properties, no blur, no shadows animated.

The implementation is in `examleaf-web/static/css/site.css` (the motion block near the top, plus the per-component rules named below) and `examleaf-web/static/js/site.js`. The component spec is `components.md`.

## 1. One timing scale

| Token | Value | Use |
|---|---|---|
| `--t-instant` | 0 ms | state colour: hover fills, checked radios, the current tab, focus rings. Colour changes are never animated. |
| `--t-fast` | 150 ms | hover and press: button and tile press, card lift, cover lift, accordion chevron, toast exit |
| `--t-base` | 220 ms | reveals: toast enter, timeline items, the stepper bar, the spine light |
| `--t-slow` | 360 ms | cross-document view transitions (the page and the named covers) |

Nothing on the site is slower than 360 ms, and no single interaction chains more than 420 ms (a 220 ms reveal plus a stagger that stops at 200 ms).

## 2. One easing family

- Enter: `--ease-enter: cubic-bezier(.2, .7, .2, 1)`: fast out of the gate, a long gentle settle. Everything that appears, lifts or arrives.
- Exit: `--ease-exit: cubic-bezier(.4, 0, 1, 1)`: starts slowly, leaves quickly. Toast dismissal and the outgoing page.
- Linear only for the busy spinner (a loop must not pulse).
- No overshoot or spring curves: the content is informational and dense.

## 3. Sequencing

- A stagger step is 40 ms at most, and at most 6 items take part. Item 7 onwards arrives with item 6 (the order timeline is the only staggered list).
- One effect per element, and at most two effects per view (a screenful). Home: the cover lift in the hero, the sticker press on the tiles; the marker draws further down, where neither is on screen.
- Nothing animates on load except the two reveals that carry news: the checkout stepper's current step and the order timeline. Neither is the largest element on its page, so neither delays LCP.

## 4. Interruption

- Press states are `:active` transforms with no JavaScript: releasing early, pressing again or pressing many times always ends in the resting state, because the state is the pointer's, not a toggle's.
- Hover lifts are transitions, so leaving mid-way reverses from wherever the element is, without a jump.
- The toast exit is idempotent: the script marks the toast as leaving and closes its `<details>` when the exit animation ends (or at once when there is none). Clicking Dismiss again while it leaves changes nothing.
- View transitions are skipped after a form is sent (the next page is an answer, not a place), on reload, and whenever the browser does not support them. The page then simply loads.

## 5. Gates

- Every animation and transition sits inside `@media (prefers-reduced-motion: no-preference)`. With reduced motion the default styles are the final, readable state: the press offset still applies instantly (it is feedback, not motion), focus rings and colour states stay, the spinner shows as a still ring beside its label.
- Scroll-driven effects are inside `@supports (animation-timeline: view())`; elsewhere the marker is drawn statically.
- `@view-transition` is inside the no-preference query; browsers without cross-document view transitions (Firefox, UC Browser, older Safari) navigate normally.
- Nothing autoplays, nothing loops except the busy spinner, nothing hijacks scrolling, and nothing works on hover only: every hover effect has a focus or tap equivalent, or is pure decoration.

## 6. The signature interactions

| | Where | What moves | Trigger | Rule |
|---|---|---|---|---|
| a. Cover stage | Home hero `.stage` | one cover lifts 14 px (`translate`, so its fan rotation stays) and its spine catches light (a `::before` sheen, opacity 0 → 1) | hover, keyboard focus, tap (each cover is the link to its book) | `--t-fast` lift, `--t-base` light, enter easing |
| b. Marker draw | `.marker[data-draw]` (Home Q.1) | the highlighter stroke scales in from the left as the phrase enters the viewport | scroll position (`animation-timeline: view()`, range entry 10–60 %) | static highlighter without support or with reduced motion |
| c. Sticker press | `.tile` | the tile drops 3 px right and down into its hard shadow | `:active` | instant state, `--t-fast` transition |
| d. View transitions | every same-origin link navigation | the page cross-fades (360 ms); a Home or 404 tile morphs into its Book page cover (`book-<subject>`, from site.css); a product card's cover morphs into the product page cover (`cover-<product id>`, a `style` attribute on the cover, which the CSP's `style-src 'unsafe-inline'` allows; if that ever goes, set the name from site.js on `pageswap`/`pagereveal`) | navigation | skipped after a form is sent (site.js, `pageswap`); names unique per page |
| e. Checkout progress | `.stepper`, `.timeline` | the current step's bar draws from the left; timeline items rise 8 px and fade in, 40 ms apart | page load | `--t-base`, enter easing |
| f. Toasts | `.toast` (Django messages) | enter: fade and 8 px slide (down on desktop, up on phones); exit: fade and slide back | page load; Dismiss | `--t-base` in, `--t-fast` out; announced once through the polite live region `#announce` |
| g. Buttons | `.btn` | 1 px press; `[aria-busy="true"]` draws a spinner (`::before`, no extra markup) before the label | `:active`; real waits only: the pay button is busy and disabled until Razorpay's window has loaded, and again while the payment is checked (shop/checkout.js) | press instant; spinner 0.8 s linear loop |

Hover-only refinements that are not in the table (the 2 px card lift, the accordion chevron turn) follow the same tokens.

## 7. Never

- No animation of the largest content element, of reading content (questions, solutions, prices, totals, form fields) or of anything while the student types.
- No parallax, no count-up numbers, no marquees, no auto-rotating content, no confetti, no skeleton shimmer or pulse: the invoice skeleton is a still placeholder, because the page does not refresh itself.
- No `width`, `height`, `top`, `left`, `box-shadow`, `filter` or `background-position` in keyframes or transitions.
- No more than two effects in a view, no stagger longer than 40 ms per item or over more than six items.
- No motion that a keyboard, a touch screen or a screen reader user cannot get the result of.

## 8. Checking it

- Chrome DevTools, Rendering: "Emulate CSS media feature prefers-reduced-motion: reduce" must leave every page usable and still, with presses and focus rings working.
- Animations panel at 10 %: the toast, the stepper and the timeline reveal must end in the same state as without motion.
- Click Dismiss on a toast five times quickly: it closes once, focus stays on the page.
- Navigate Home → a tile, Catalogue → a card, and back: the cover morphs; send any form: no transition.
- Firefox: no transitions, nothing broken.
