// Lab INP: Event Timing entries for real clicks and key presses, at 4x CPU slowdown, 375 px wide (the Lighthouse mobile profile).
import { launch, open, sleep, SP, BASE, cookies } from './lib.mjs';
import fs from 'node:fs';
const b = await launch();
const out = {};
async function session(name, url, auth, steps) {
  const ctx = await b.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2, hasTouch: false });
  if (auth) for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
  const client = await page.createCDPSession();
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await page.evaluateOnNewDocument(() => {
    window.__ev = [];
    new PerformanceObserver((list) => { for (const e of list.getEntries()) window.__ev.push({ name: e.name, id: e.interactionId, dur: e.duration, delay: e.processingStart - e.startTime, proc: e.processingEnd - e.processingStart, target: e.target && (e.target.tagName.toLowerCase() + (e.target.id ? '#' + e.target.id : '') + '.' + String(e.target.className || '').split(' ')[0]) }); }).observe({ type: 'event', durationThreshold: 16, buffered: true });
  });
  await page.goto(BASE + url, { waitUntil: 'networkidle0' }); await sleep(800);
  for (const s of steps) { try { await s(page); } catch (e) { console.log(name, 'step error', String(e).slice(0, 140)); } await sleep(450); }
  const ev = await page.evaluate(() => window.__ev);
  const by = {};
  for (const e of ev) if (e.id) { if (!by[e.id] || e.dur > by[e.id].dur) by[e.id] = e; }
  const list = Object.values(by).map((e) => ({ type: e.name, target: e.target, dur: Math.round(e.dur), inputDelay: Math.round(e.delay), processing: Math.round(e.proc) }));
  const worst = list.reduce((m, e) => Math.max(m, e.dur), 0);
  out[name] = { interactions: list.length, inpMs: worst, list: list.sort((a, c) => c.dur - a.dur).slice(0, 5) };
  console.log(name.padEnd(10), 'interactions logged', list.length, '| worst', worst, 'ms', JSON.stringify(out[name].list[0] || ''));
  await ctx.close();
}
// click the first element whose accessible text/aria-label matches
const clickText = (re, sel = 'button,a,summary,label,[role=button]') => async (p) => {
  const h = await p.evaluateHandle((re, sel) => [...document.querySelectorAll(sel)].find((e) => new RegExp(re, 'i').test((e.getAttribute('aria-label') || e.textContent || '').trim()) && e.getBoundingClientRect().width > 0), re, sel);
  const el = h.asElement(); if (!el) throw new Error('no element ' + re);
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' })); await sleep(200); await el.click();
};
const typeIn = (sel, text) => async (p) => { await p.click(sel); await p.keyboard.type(text, { delay: 60 }); };
await session('home', '/', false, [clickText('^Menu'), clickText('^Close'), clickText('How|delivery|FAQ|\\?', 'summary'), clickText('How|delivery|FAQ|\\?', 'summary')]);
await session('shop', '/shop/', false, [clickText('Sample Papers|Solutions', 'a,button,label')]);
await session('product', '/shop/physics-sample-papers-2027/', false, [clickText('One copy more'), clickText('One copy more'), clickText('One copy fewer'), typeIn('#copies', '3')]);
await session('cart', '/cart/', true, [clickText('One copy more'), clickText('One copy fewer'), clickText('^Remove'), clickText('Keep')]);
await session('login', '/account/login/', false, [typeIn('#phone', '9876543210'), clickText('Log in with email and password', 'summary')]);
await session('checkout', '/checkout/', true, [typeIn('#name', 'Test Student'), typeIn('#pin', '781001')]);
await session('paper', '/s/PHY-E01/', true, [clickText('Instructions', 'summary'), typeIn('input[name=marks_obtained]', '45')]);
await session('account', '/account/', true, [clickText('^Menu'), clickText('^Close')]);
await b.close();
fs.writeFileSync(SP + '/inp-results.json', JSON.stringify(out, null, 1));
