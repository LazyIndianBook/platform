// Functions that run inside the page (page.evaluate). Plain functions, no closures over Node variables.

export const selOf = `(e) => { if (!e || !e.tagName) return String(e); let s = e.tagName.toLowerCase(); if (e.id) s += '#' + e.id; const c = (typeof e.className === 'string' ? e.className : '').trim().split(/\\s+/).filter(Boolean).slice(0, 2); if (c.length) s += '.' + c.join('.'); return s; }`;

// Static document checks: headings, landmarks, images, icons, ids, aria references, targets, languages, inputs.
export function staticChecks() {
  const sel = (e) => { if (!e || !e.tagName) return String(e); let s = e.tagName.toLowerCase(); if (e.id) s += '#' + e.id; const c = (typeof e.className === 'string' ? e.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2); if (c.length) s += '.' + c.join('.'); return s; };
  const visible = (e) => { const cs = getComputedStyle(e); const r = e.getBoundingClientRect(); return cs.display !== 'none' && cs.visibility !== 'hidden' && (r.width > 0 || r.height > 0) && !e.closest('[hidden],[inert]'); };
  const txt = (e, n = 70) => (e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const out = {};
  // headings
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]')];
  out.headings = hs.map((h) => ({ level: Number(h.tagName[1] || h.getAttribute('aria-level')), text: txt(h), visible: visible(h), sel: sel(h) }));
  const seq = out.headings.filter((h) => h.visible);
  out.headingIssues = [];
  if (seq.filter((h) => h.level === 1).length !== 1) out.headingIssues.push(`h1 count = ${seq.filter((h) => h.level === 1).length}`);
  seq.forEach((h, i) => { if (i && h.level - seq[i - 1].level > 1) out.headingIssues.push(`skips from h${seq[i - 1].level} to h${h.level}: "${h.text}"`); if (!h.text) out.headingIssues.push(`empty heading ${h.sel}`); });
  // landmarks
  const lm = [];
  for (const e of document.querySelectorAll('header,nav,main,footer,aside,section,form,search,[role=banner],[role=navigation],[role=main],[role=contentinfo],[role=complementary],[role=region],[role=search],[role=form]')) {
    const role = e.getAttribute('role') || ({ HEADER: 'banner', NAV: 'navigation', MAIN: 'main', FOOTER: 'contentinfo', ASIDE: 'complementary', SECTION: 'region', FORM: 'form', SEARCH: 'search' })[e.tagName];
    const name = e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') && document.getElementById(e.getAttribute('aria-labelledby').split(' ')[0])?.textContent.trim()) || '';
    // header/footer are banner/contentinfo only when not inside article/section/main
    let eff = role;
    if (['banner', 'contentinfo'].includes(role) && e.closest('article,aside,main,nav,section')) eff = 'generic';
    if (['region', 'form'].includes(role) && !name) eff = 'generic';
    if (eff !== 'generic') lm.push({ role: eff, name, sel: sel(e) });
  }
  out.landmarks = lm;
  // images
  out.images = [...document.querySelectorAll('img,input[type=image],area,[role=img]')].map((e) => ({ sel: sel(e), alt: e.getAttribute('alt'), ariaLabel: e.getAttribute('aria-label'), src: (e.currentSrc || e.src || '').split('/').slice(-1)[0].slice(0, 50), inLink: !!e.closest('a,button'), w: Math.round(e.getBoundingClientRect().width) }));
  out.imagesMissingAlt = out.images.filter((i) => i.alt === null && !i.ariaLabel && i.sel.startsWith('img'));
  // svg icons exposed to AT
  out.svgExposed = [...document.querySelectorAll('svg')].filter((s) => !s.closest('[aria-hidden=true]') && s.getAttribute('aria-hidden') !== 'true' && !s.classList.contains('icon-sprite') && !s.closest('.icon-sprite') && !s.getAttribute('aria-label') && !s.querySelector('title') && visible(s)).map((s) => sel(s) + ' in ' + sel(s.parentElement));
  // duplicate ids
  const ids = {}; document.querySelectorAll('[id]').forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
  out.duplicateIds = Object.entries(ids).filter(([, n]) => n > 1).map(([k]) => k);
  // aria references that do not resolve
  out.brokenRefs = [];
  for (const attr of ['aria-describedby', 'aria-labelledby', 'aria-controls', 'aria-owns', 'aria-activedescendant', 'for', 'form']) {
    document.querySelectorAll(`[${attr}]`).forEach((e) => { for (const id of e.getAttribute(attr).split(/\s+/).filter(Boolean)) { if (!document.getElementById(id)) out.brokenRefs.push(`${sel(e)} ${attr}="${id}"`); } });
  }
  // interactive targets
  const inter = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[tabindex]:not([tabindex="-1"])')].filter(visible);
  out.interactiveCount = inter.length;
  out.targets = [];
  for (const e of inter) {
    let r = e.getBoundingClientRect(); let owner = e;
    if (r.width <= 2 && r.height <= 2) { const lab = (e.labels && e.labels[0]) || (e.parentElement && [...e.parentElement.children].find((s) => s !== e && s.tagName === 'LABEL' && visible(s))); if (lab) { r = lab.getBoundingClientRect(); owner = lab; } }
    const inline = e.tagName === 'A' && getComputedStyle(e).display === 'inline' && e.parentElement && (e.parentElement.textContent.trim().length > e.textContent.trim().length + 3);
    if ((r.width < 24 || r.height < 24) && !inline) out.targets.push({ sel: sel(e), name: (e.getAttribute('aria-label') || txt(e, 30)), w: Math.round(r.width), h: Math.round(r.height), level: 'below 24x24 (2.5.8 AA)' });
    else if ((r.width < 44 || r.height < 44) && !inline) out.targets.push({ sel: sel(e), name: (e.getAttribute('aria-label') || txt(e, 30)), w: Math.round(r.width), h: Math.round(r.height), level: 'below 44x44 (best practice, 2.5.5 AAA)' });
  }
  // language of parts: Bengali/Assamese script outside a bn/as lang
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); const bad = []; let n;
  while ((n = walker.nextNode())) { if (/[ঀ-৿]/.test(n.nodeValue) && !n.parentElement.closest('script,style')) { const l = n.parentElement.closest('[lang]'); const lang = l ? l.getAttribute('lang') : ''; if (!/^(bn|as)/i.test(lang)) bad.push(`${sel(n.parentElement)} lang="${lang}": ${n.nodeValue.trim().slice(0, 30)}`); } }
  out.bengaliWithoutLang = bad.slice(0, 8);
  out.htmlLang = document.documentElement.lang;
  out.title = document.title;
  // inputs: label, autocomplete
  out.inputs = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')].filter(visible).map((e) => ({ sel: sel(e), type: e.type, name: e.name, autocomplete: e.getAttribute('autocomplete'), required: e.required, ariaRequired: e.getAttribute('aria-required'), labelled: !!((e.labels && e.labels.length) || e.getAttribute('aria-label') || e.getAttribute('aria-labelledby')), invalid: e.getAttribute('aria-invalid'), describedby: e.getAttribute('aria-describedby') }));
  // links with identical text and different destinations; vague link text
  const links = {}; document.querySelectorAll('a[href]').forEach((a) => { if (!visible(a)) return; const t = (a.getAttribute('aria-label') || a.textContent).replace(/\s+/g, ' ').trim().toLowerCase(); (links[t] ||= new Set()).add(a.getAttribute('href')); });
  out.sameTextDifferentTarget = Object.entries(links).filter(([t, h]) => t && h.size > 1).map(([t, h]) => `"${t}" -> ${[...h].slice(0, 4).join(' | ')}`);
  out.vagueLinks = [...document.querySelectorAll('a[href]')].filter((a) => visible(a) && /^(click here|here|more|read more|learn more|link)$/i.test(a.textContent.trim())).map(sel);
  // live regions and status roles present at load
  out.liveRegions = [...document.querySelectorAll('[aria-live],[role=alert],[role=status],[role=log]')].map((e) => `${sel(e)} aria-live=${e.getAttribute('aria-live')} role=${e.getAttribute('role')} text="${txt(e, 50)}"`);
  // positive tabindex, autofocus, accesskey
  out.positiveTabindex = [...document.querySelectorAll('[tabindex]')].filter((e) => Number(e.getAttribute('tabindex')) > 0).map(sel);
  out.autofocus = [...document.querySelectorAll('[autofocus]')].map(sel);
  out.metaViewport = document.querySelector('meta[name=viewport]')?.content;
  out.zoomBlocked = /user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b/.test(out.metaViewport || '');
  return out;
}

// Describe the focused element: where it is, whether it shows a ring, whether anything covers it.
export function focusInfo() {
  const sel = (e) => { if (!e || !e.tagName) return String(e); let s = e.tagName.toLowerCase(); if (e.id) s += '#' + e.id; const c = (typeof e.className === 'string' ? e.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2); if (c.length) s += '.' + c.join('.'); return s; };
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return { none: true, tag: el && el.tagName };
  const lum = (rgb) => { const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
  const bgOf = (e) => { for (let n = e; n; n = n.parentElement) { const cs = getComputedStyle(n); const c = parse(cs.backgroundColor); if (cs.backgroundImage !== 'none') return { unknown: true, via: sel(n) }; if (c && c.a > 0.5) return { rgb: c.rgb, via: sel(n) }; } return { rgb: [255, 255, 255], via: 'canvas' }; };
  let target = el; let r = el.getBoundingClientRect(); const cs0 = getComputedStyle(el);
  let ringOn = 'self';
  const hiddenControl = (r.width <= 2 && r.height <= 2) || parseFloat(cs0.opacity) === 0 || (cs0.position === 'absolute' && cs0.clip && cs0.clip !== 'auto');
  if (hiddenControl) { // a visually hidden control (the Menu checkbox): its ring is drawn on a sibling
    const sibs = [...el.parentElement.children].filter((s) => s !== el && getComputedStyle(s).display !== 'none');
    const withRing = sibs.find((s) => { const c = getComputedStyle(s); return c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0; });
    const lab = withRing || (el.labels && el.labels[0]) || sibs.find((s) => s.tagName === 'LABEL');
    if (lab) { target = lab; r = lab.getBoundingClientRect(); ringOn = sel(lab); }
  }
  const cs = getComputedStyle(target);
  const hasOutline = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0;
  const hasShadow = cs.boxShadow && cs.boxShadow !== 'none';
  // some controls wear the ring on a wrapper (label.card:has(input:focus-visible), .input-prefix:focus-within)
  let wrapperRing = null;
  for (let n = target.parentElement, d = 0; n && d < 3; n = n.parentElement, d++) { const c = getComputedStyle(n); if (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0 && n.matches(':has(:focus-visible), :focus-within')) { wrapperRing = sel(n); break; } }
  const vw = innerWidth, vh = innerHeight;
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const pts = [[cx, cy], [cx, r.top + 5], [cx, r.bottom - 5], [r.left + 5, cy], [r.right - 5, cy]];
  const covers = [];
  let coveredPts = 0; let inView = 0;
  for (const [x, y] of pts) {
    if (x < 0 || y < 0 || x > vw || y > vh) continue; inView++;
    const top = document.elementFromPoint(x, y);
    if (top && !(target.contains(top) || top.contains(target) || el.contains(top) || top.contains(el) || (top.tagName === 'LABEL' && top.control === el))) { coveredPts++; covers.push(sel(top)); }
  }
  const ringColor = hasOutline ? parse(cs.outlineColor) : null;
  let contrast = null;
  if (ringColor) { const bg = bgOf(target.parentElement || target); if (bg.rgb) { const l1 = lum(ringColor.rgb), l2 = lum(bg.rgb); contrast = Number(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)).toFixed(2)); } else contrast = 'bg image'; }
  const text = (el.getAttribute('aria-label') || el.value || el.textContent || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  return {
    sel: sel(el), tag: el.tagName, type: el.type || null, text, href: el.getAttribute('href'),
    focusVisible: el.matches(':focus-visible'), ringOn, outline: `${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor} off ${cs.outlineOffset}`, hasShadow: !!hasShadow, wrapperRing,
    indicator: !!(hasOutline || hasShadow || wrapperRing), ringContrast: contrast,
    rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
    inViewport: r.top >= -2 && r.bottom <= vh + 2 && r.left >= -2 && r.right <= vw + 2, partlyOffscreen: !(r.top >= -2 && r.bottom <= vh + 2 && r.left >= -2 && r.right <= vw + 2), targetSel: sel(target), hiddenControl,
    coveredPoints: `${coveredPts}/${inView}`, fullyCovered: inView > 0 && coveredPts === inView, partlyCovered: coveredPts > 0 && coveredPts < inView, coveredBy: [...new Set(covers)].slice(0, 3),
    tabindex: el.getAttribute('tabindex'), scrollY: Math.round(scrollY),
  };
}
