// End to end: a log-in link with next=/..//attacker.invalid/phish. After a genuine log-in (email code) where does the browser go?
// Requests to attacker.invalid are recorded and aborted (nothing leaves the machine; the name does not resolve anyway).
import fs from 'node:fs';
import { launch, sleep, SP, BASE } from './lib.mjs';
const EMAIL = 'nx-review-temp@example.com';
const log = () => fs.readFileSync(SP + '/django.log', 'utf8');
async function emailedCode(after, timeout = 40000) { const end = Date.now() + timeout; while (Date.now() < end) { const text = log(); const start = text.lastIndexOf(`To: ${EMAIL}`); if (start >= after && start !== -1) { const m = /^(\d{6})\r?$/m.exec(text.slice(start)); if (m) return m[1]; } await sleep(250); } throw new Error('no code'); }
const b = await launch();
const out = {};
for (const [label, next] of [['dotdot', '/..//attacker.invalid/phish'], ['dot', '/.//attacker.invalid/phish'], ['plain-relative-to-protect', '//attacker.invalid/phish'], ['normal', '/shop/']]) {
  const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 375, height: 812 });
  const hits = []; const navs = [];
  await page.setRequestInterception(true);
  page.on('request', (r) => { if (new URL(r.url()).hostname === 'attacker.invalid') { hits.push(`${r.method()} ${r.url()} (navigation=${r.isNavigationRequest()})`); return r.abort(); } r.continue(); });
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) navs.push(f.url().replace(BASE, '')); });
  await page.goto(`${BASE}/account/login/?next=${encodeURIComponent(next).replace(/%2F/g, '/')}`, { waitUntil: 'networkidle0' });
  const after = log().length;
  await page.evaluate(() => [...document.querySelectorAll('button')].find((e) => /^Email me a code/.test(e.textContent.trim()))?.click()); await sleep(500);
  await page.type('input[type=email]', EMAIL); await page.keyboard.press('Enter');
  const code = await emailedCode(after); await sleep(600);
  await page.keyboard.type(code); await sleep(300); await page.keyboard.press('Enter'); await sleep(3500);
  out[label] = { next, requestedAttackerHost: hits, mainFrameNavigations: navs.slice(-4) };
  console.log(label.padEnd(26), 'next =', next, '\n   attacker.invalid requested:', JSON.stringify(hits), '\n   navigations:', JSON.stringify(navs.slice(-3)));
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/sec-redirect.json', JSON.stringify(out, null, 1));
