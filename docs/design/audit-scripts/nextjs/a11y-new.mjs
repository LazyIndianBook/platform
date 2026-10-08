// What the build half added: the authenticator QR, the signed-in devices list, Log in again alert, Coming soon badges, skip link, h1 focus.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const AXE = fs.readFileSync(SP + '/node_modules/axe-core/axe.min.js', 'utf8');
const out = {};
const b = await launch();
const axe = async (page) => { await page.evaluate(AXE); return page.evaluate(async () => { const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } }); return { violations: r.violations.map((v) => `${v.id}(${v.nodes.length}): ${v.nodes[0].target.join(' ').slice(0, 80)}`), incomplete: r.incomplete.map((v) => `${v.id}(${v.nodes.length})`) }; }); };
// 1. authenticator app page
{
  const { ctx, page } = await open(b, '/account/2fa/', { auth: true }); await sleep(800);
  out.twofa = await page.evaluate(() => { const q = document.querySelector('[role=img], canvas, svg[aria-label]:not([aria-hidden])'); return { qr: [...document.querySelectorAll('main [role=img], main canvas')].map((e) => `${e.tagName.toLowerCase()} role=${e.getAttribute('role')} aria-label="${e.getAttribute('aria-label')}" ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`), text: document.querySelector('main').innerText.replace(/\s+/g, ' ').slice(0, 500), codeBox: [...document.querySelectorAll('main code, main input[readonly]')].map((e) => (e.value || e.textContent).slice(0, 12) + '…') }; });
  out.twofaAxe = await axe(page);
  await page.screenshot({ path: SP + '/shots/twofa-375.png', fullPage: true });
  await ctx.close();
}
// 2. security: devices list
{
  const { ctx, page } = await open(b, '/account/security/', { auth: true }); await sleep(800);
  out.devices = await page.evaluate(() => { const h = [...document.querySelectorAll('main h2, main h3')].find((e) => /device|signed in|browsers/i.test(e.textContent)); const sec = h && h.closest('section, div[data-slot=card]'); return { heading: h && h.textContent.trim(), html: sec ? sec.innerText.replace(/\s+/g, ' ').slice(0, 600) : null, buttons: sec ? [...sec.querySelectorAll('button')].map((x) => `${x.textContent.trim()} ${Math.round(x.getBoundingClientRect().width)}x${Math.round(x.getBoundingClientRect().height)}`) : [], table: sec ? !!sec.querySelector('table') : null, list: sec ? [...sec.querySelectorAll('ul,ol,table')].map((e) => e.tagName.toLowerCase() + (e.getAttribute('aria-label') ? `[${e.getAttribute('aria-label')}]` : '')) : [] }; });
  out.securityAxe = await axe(page);
  await ctx.close();
}
// 3. Download my data: the log-in-again alert (the session is older than 5 minutes)
{
  const { ctx, page } = await open(b, '/account/privacy/', { auth: true }); await sleep(800);
  await page.evaluate(() => [...document.querySelectorAll('main button')].find((e) => /Download my data/.test(e.textContent))?.click()); await sleep(1500);
  out.reauth = await page.evaluate(() => ({ alerts: [...document.querySelectorAll('[role=alert],[role=status]')].map((a) => `${a.getAttribute('role')}: ${a.textContent.trim().slice(0, 200)}`), active: document.activeElement.tagName.toLowerCase() + '#' + document.activeElement.id }));
  out.reauthAxe = await axe(page);
  await page.screenshot({ path: SP + '/shots/reauth-alert.png' });
  await ctx.close();
}
// 4. revision: Coming soon badges
{
  const { ctx, page } = await open(b, '/revision/', { auth: false }); await sleep(600);
  out.revision = await page.evaluate(() => { const cs = [...document.querySelectorAll('main *')].filter((e) => e.children.length === 0 && /Coming soon/i.test(e.textContent)); return { comingSoonCount: cs.length, sample: cs.slice(0, 3).map((e) => e.outerHTML.slice(0, 200)), tables: [...document.querySelectorAll('main table')].map((t) => ({ caption: t.querySelector('caption')?.textContent.trim().slice(0, 60) || null, wrapRole: t.closest('[data-slot=table-wrap]')?.getAttribute('role'), wrapLabel: t.closest('[data-slot=table-wrap]')?.getAttribute('aria-label')?.slice(0, 50), wrapTabindex: t.closest('[data-slot=table-wrap]')?.getAttribute('tabindex'), wrapScrollable: (() => { const w = t.closest('[data-slot=table-wrap]'); return w ? w.scrollWidth > w.clientWidth : null; })() })), details: [...document.querySelectorAll('main details')].length };
  });
  await ctx.close();
}
// 5. skip link and h1 focus
{
  const { ctx, page } = await open(b, '/shop/', { auth: false }); await sleep(500);
  await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
  await page.keyboard.press('Tab'); await sleep(80);
  const first = await page.evaluate(() => { const a = document.activeElement; const r = a.getBoundingClientRect(); return { text: a.textContent.trim(), href: a.getAttribute('href'), top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height) }; });
  await page.screenshot({ path: SP + '/shots/skip-link.png', clip: { x: 0, y: 0, width: 375, height: 140 } });
  await page.keyboard.press('Enter'); await sleep(300);
  out.skip = { first, afterEnter: await page.evaluate(() => ({ hash: location.hash, active: document.activeElement.tagName.toLowerCase() + '#' + document.activeElement.id, tabindex: document.activeElement.getAttribute('tabindex'), scrollY: Math.round(scrollY) })) };
  await page.keyboard.press('Tab'); await sleep(80);
  out.skip.nextTab = await page.evaluate(() => { const a = document.activeElement; return `${a.tagName.toLowerCase()} "${(a.getAttribute('aria-label') || a.textContent).trim().slice(0, 30)}" insideMain=${!!a.closest('main')}`; });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-new.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
