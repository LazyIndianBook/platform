// Fresh log-in by code (so the 5-minute rule is met), then the deletion request and Keep my account, with focus, toasts and states.
import fs from 'node:fs';
import { launch, sleep, SP, BASE } from './lib.mjs';
const EMAIL = 'nx-review-temp@example.com';
const log = () => fs.readFileSync(SP + '/django.log', 'utf8');
async function emailedCode(after, timeout = 60000) { const end = Date.now() + timeout; while (Date.now() < end) { const text = log(); const start = text.lastIndexOf(`To: ${EMAIL}`); if (start >= after && start !== -1) { const m = /^(\d{6})\r?$/m.exec(text.slice(start)); if (m) return m[1]; } await sleep(250); } throw new Error('no code'); }
const out = {};
const b = await launch();
const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 });
await page.goto(BASE + '/account/login/?next=/account/privacy/', { waitUntil: 'networkidle0' });
const after = log().length;
await page.evaluate(() => [...document.querySelectorAll('button')].find((e) => /^Email me a code/.test(e.textContent.trim()))?.click()); await sleep(500);
await page.type('input[type=email]', EMAIL); await page.keyboard.press('Enter');
const code = await emailedCode(after); await sleep(600);
await page.keyboard.type(code); await sleep(300); await page.keyboard.press('Enter'); await sleep(3500);
out.landed = page.url().replace(BASE, '');
const snap = () => page.evaluate(() => ({ alerts: [...document.querySelectorAll('[role=alert],[role=status]')].map((a) => `${a.getAttribute('role')}: ${a.textContent.trim().slice(0, 120)}`), toast: [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.textContent.trim().slice(0, 100)), active: `${document.activeElement.tagName.toLowerCase()}#${document.activeElement.id}`, buttons: [...document.querySelectorAll('main button')].map((x) => x.textContent.trim()).filter((t) => /Delete|Keep|Download/.test(t)) }));
// request the deletion (tick the box, then the button)
await page.evaluate(() => document.querySelector('#confirm').scrollIntoView({ block: 'center' }));
await page.focus('#confirm'); await page.keyboard.press('Space'); await sleep(150);
out.checkboxChecked = await page.$eval('#confirm', (e) => e.checked);
const del = await page.evaluateHandle(() => [...document.querySelectorAll('main button')].find((x) => /Delete my account/.test(x.textContent)));
await del.asElement().click(); await sleep(2500);
out.afterDelete = await snap(); out.afterDeleteUrl = page.url().replace(BASE, '');
await page.screenshot({ path: SP + '/shots/deletion-requested.png' });
// keep the account
const keep = await page.evaluateHandle(() => [...document.querySelectorAll('main button')].find((x) => /Keep my account/.test(x.textContent)));
if (keep.asElement()) { await keep.asElement().click(); await sleep(2500); out.afterKeep = await snap(); }
await ctx.close(); await b.close();
fs.writeFileSync(SP + '/a11y-delete.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
