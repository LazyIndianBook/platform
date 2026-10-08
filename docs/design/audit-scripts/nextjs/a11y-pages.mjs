// Per page at 375 px: static checks (headings, landmarks, images, targets, ids), unnamed nodes in the accessibility tree,
// axe-core (wcag2a/aa, 21, 22aa, best-practice) and a real Tab walk with a probe after every press.
// ONLY=id1,id2 to run some; EXTRA='[{"id":..,"url":..,"auth":..}]' to add pages.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
import { staticChecks, focusInfo } from './inpage.mjs';
const AXE = fs.readFileSync(SP + '/node_modules/axe-core/axe.min.js', 'utf8');
const PAGES = [
  { id: 'home', url: '/' }, { id: 'about', url: '/about/' }, { id: 'book', url: '/books/physics-2027/' }, { id: 'shop', url: '/shop/' },
  { id: 'product', url: '/shop/physics-sample-papers-2027/' }, { id: 'schoolorders', url: '/shop/school-orders/' }, { id: 'lookup', url: '/orders/lookup/' },
  { id: 'contact', url: '/contact/' }, { id: 'privacy', url: '/privacy/' }, { id: 'terms', url: '/terms/' }, { id: 'refunds', url: '/refunds/' }, { id: 'shipping', url: '/shipping/' },
  { id: 'revision', url: '/revision/' }, { id: 'paper-open', url: '/s/PHY-E01/' }, { id: 'paper-gate', url: '/s/PHY-E02/' },
  { id: 'login', url: '/account/login/' }, { id: 'signup', url: '/account/signup/' }, { id: 'pwreset', url: '/account/password/reset/' },
  { id: 'notfound', url: '/no-such-page-xyz/' }, { id: 'offline', url: '/offline/' }, { id: 'consent-bogus', url: '/c/bogus-token/' }, { id: 'ordertoken-bogus', url: '/orders/t/bogus-token/' },
  { id: 'account', url: '/account/', auth: true }, { id: 'record', url: '/account/record/', auth: true }, { id: 'orders', url: '/account/orders/', auth: true },
  { id: 'order', url: '/account/orders/EL-2026-000003/', auth: true }, { id: 'details', url: '/account/details/', auth: true }, { id: 'addresses', url: '/account/addresses/', auth: true },
  { id: 'security', url: '/account/security/', auth: true }, { id: 'twofa', url: '/account/2fa/', auth: true }, { id: 'privacy-acct', url: '/account/privacy/', auth: true },
  { id: 'teacher', url: '/account/teacher/', auth: true }, { id: 'cart', url: '/cart/', auth: true }, { id: 'checkout', url: '/checkout/', auth: true },
  { id: 'pay', url: '/checkout/EL-2026-000003/pay/', auth: true }, { id: 'revision-auth', url: '/revision/', auth: true }, { id: 'paper-auth', url: '/s/PHY-E02/', auth: true },
  { id: 'paper-open-auth', url: '/s/PHY-E01/', auth: true },
];
if (process.env.EXTRA) PAGES.push(...JSON.parse(process.env.EXTRA));
const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
const OUTF = SP + '/a11y-pages.json';
const results = fs.existsSync(OUTF) && only ? JSON.parse(fs.readFileSync(OUTF, 'utf8')) : {};
const save = () => fs.writeFileSync(OUTF, JSON.stringify(results, null, 1));
const browser = await launch();

async function axOfActive(client) {
  try {
    const { result } = await client.send('Runtime.evaluate', { expression: 'document.activeElement' });
    if (!result.objectId) return {};
    const { nodes } = await client.send('Accessibility.getPartialAXTree', { objectId: result.objectId, fetchRelatives: false });
    const n = nodes[0] || {};
    const props = Object.fromEntries((n.properties || []).map((p) => [p.name, p.value && p.value.value]));
    return { role: n.role && n.role.value, name: n.name && n.name.value, description: n.description && n.description.value, props: { expanded: props.expanded, checked: props.checked, invalid: props.invalid, required: props.required, disabled: props.disabled } };
  } catch (e) { return { err: String(e).slice(0, 80) }; }
}
async function tabWalk(page, client, max = 140) {
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); scrollTo(0, 0); });
  const stops = []; const seen = new Set(); const repeats = {};
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab'); await sleep(50);
    let info = await page.evaluate(focusInfo);
    for (let k = 0; k < 8 && !info.none; k++) {
      await sleep(50); const again = await page.evaluate(focusInfo);
      const same = again.sel === info.sel && again.rect.x === info.rect.x && again.rect.y === info.rect.y && again.scrollY === info.scrollY;
      info = again; if (same) break;
    }
    if (info.none) { stops.push({ i, wrapped: true }); break; }
    const key = `${info.sel}|${info.text}|${info.href}|${info.rect.x},${info.rect.y + info.scrollY}`;
    if (seen.has(key)) { repeats[key] = (repeats[key] || 0) + 1; if (['date', 'time', 'month', 'week', 'datetime-local'].includes(info.type) && repeats[key] <= 5) continue; stops.push({ i, repeated: info.sel }); break; }
    seen.add(key);
    const ax = await axOfActive(client);
    stops.push({ i, ...info, role: ax.role, name: ax.name, ax: ax.props });
  }
  return stops;
}
function summarise(stops) {
  const real = stops.filter((s) => s.sel); const issues = [];
  real.forEach((s, k) => {
    if (!s.indicator) issues.push(`#${s.i} ${s.sel} "${s.text}": no visible focus indicator (outline ${s.outline})`);
    if (s.indicator && typeof s.ringContrast === 'number' && s.ringContrast < 3) issues.push(`#${s.i} ${s.sel}: focus ring contrast ${s.ringContrast}:1 (< 3:1)`);
    if (s.fullyCovered) issues.push(`#${s.i} ${s.sel} "${s.text}": focus fully covered by ${s.coveredBy.join(', ')} (2.4.11)`);
    else if (s.partlyCovered) issues.push(`#${s.i} ${s.sel} "${s.text}": focus partly covered by ${s.coveredBy.join(', ')} (${s.coveredPoints})`);
    if (s.partlyOffscreen && !s.fullyCovered) issues.push(`#${s.i} ${s.sel} "${s.text}": not fully inside the viewport after focus (rect ${JSON.stringify(s.rect)})`);
    if (!s.name && s.tag.toLowerCase() !== 'input') issues.push(`#${s.i} ${s.sel}: focusable with no accessible name (role ${s.role})`);
    if (s.tabindex && Number(s.tabindex) > 0) issues.push(`#${s.i} ${s.sel}: positive tabindex`);
    const prev = real[k - 1];
    if (prev && s.rect.y + s.scrollY < prev.rect.y + prev.scrollY - 60 && s.rect.x < prev.rect.x + 100 && prev.rect.h !== 0) issues.push(`#${s.i} ${s.sel}: moves back up the page from ${prev.sel} (focus order vs visual order)`);
  });
  return { stops: real.length, issues };
}
const trim = (s) => (s.sel ? { i: s.i, sel: s.sel, role: s.role, name: s.name, text: s.text, indicator: s.indicator, contrast: s.ringContrast, y: s.rect.y + s.scrollY, h: s.rect.h, w: s.rect.w, covered: s.fullyCovered ? 'full' : s.partlyCovered ? 'part' : undefined } : s);

for (const p of PAGES) {
  if (only && !only.includes(p.id)) continue;
  let ctx;
  try {
    const o = await open(browser, p.url, { auth: Boolean(p.auth) });
    ctx = o.ctx; const { page, errors, status } = o;
    const client = await page.createCDPSession(); await client.send('Accessibility.enable');
    await page.evaluate(() => document.fonts.ready); await sleep(400);
    const r = (results[p.id] = { url: p.url, finalUrl: page.url().replace('http://localhost:3003', ''), status, auth: Boolean(p.auth) });
    r.consoleErrors = errors;
    r.static = await page.evaluate(staticChecks);
    const { nodes } = await client.send('Accessibility.getFullAXTree');
    const INTER = new Set(['button', 'link', 'checkbox', 'radio', 'textbox', 'combobox', 'switch', 'spinbutton', 'searchbox', 'menuitem', 'tab', 'option', 'slider', 'img']);
    r.unnamed = [];
    for (const n of nodes) {
      if (n.ignored || !n.role) continue;
      if (INTER.has(n.role.value) && !(n.name && n.name.value && n.name.value.trim())) {
        let desc = ''; try { const d = await client.send('DOM.describeNode', { backendNodeId: n.backendDOMNodeId }); desc = `<${d.node.localName} ${(d.node.attributes || []).join(' ').slice(0, 100)}>`; } catch {}
        r.unnamed.push(`${n.role.value} ${desc}`);
      }
    }
    await page.evaluate(AXE);
    r.axe = await page.evaluate(async () => {
      const res = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } });
      const short = (n) => ({ target: n.target.join(' ').slice(0, 140), html: n.html.slice(0, 180), why: (n.failureSummary || '').replace(/\s+/g, ' ').slice(0, 240) });
      return { version: axe.version, violations: res.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, count: v.nodes.length, nodes: v.nodes.slice(0, 4).map(short) })), incomplete: res.incomplete.map((v) => ({ id: v.id, help: v.help, count: v.nodes.length, nodes: v.nodes.slice(0, 2).map(short) })), passes: res.passes.length };
    });
    const stops = await tabWalk(page, client);
    r.tab = { ...summarise(stops), order: stops.map(trim) };
    console.log(p.id.padEnd(18), 'status', status, '| axe', r.axe.violations.map((v) => `${v.id}(${v.count})`).join(',') || 'none', '| review', r.axe.incomplete.map((v) => `${v.id}(${v.count})`).join(',') || '-', '| tab stops', r.tab.stops, 'issues', r.tab.issues.length, '| unnamed', r.unnamed.length, '| h1', r.static.headings.filter((h) => h.level === 1 && h.visible).length, r.static.headingIssues.join(';'));
    save();
  } catch (e) { console.log(p.id, 'ERROR', String(e).slice(0, 200)); results[p.id] = { error: String(e).slice(0, 300) }; save(); }
  finally { if (ctx) await ctx.close(); }
}
await browser.close();
