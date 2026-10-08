// The Radix dialogs (cart Remove, Cancel the order) with real key presses, and the same dialog in a 320x256 viewport (400 % zoom).
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const out = {};
const b = await launch();
const desc = (page) => page.evaluate(() => { const a = document.activeElement; const r = a.getBoundingClientRect(); return `${a.tagName.toLowerCase()}${a.id ? '#' + a.id : ''} "${(a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 30)}" y=${Math.round(r.top)} inDialog=${!!a.closest('[role=dialog]')}`; });
const dialogInfo = (page) => page.evaluate(() => {
  const d = document.querySelector('[role=dialog]'); if (!d) return null;
  const name = d.getAttribute('aria-labelledby') && document.getElementById(d.getAttribute('aria-labelledby'))?.textContent;
  const desc = d.getAttribute('aria-describedby') && document.getElementById(d.getAttribute('aria-describedby'))?.textContent;
  const r = d.getBoundingClientRect();
  const hiddenSiblings = [...document.body.children].filter((e) => e.getAttribute('aria-hidden') === 'true' || e.hasAttribute('inert') || e.hasAttribute('data-aria-hidden')).map((e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : ''));
  return { role: d.getAttribute('role'), ariaModal: d.getAttribute('aria-modal'), name, description: desc && desc.slice(0, 120), rect: { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), h: Math.round(r.height) }, vh: innerHeight, vw: innerWidth, hiddenSiblings, bodyPointerEvents: getComputedStyle(document.body).pointerEvents, bodyOverflow: getComputedStyle(document.body).overflow, dataState: d.getAttribute('data-state') };
});
async function tabTo(page, re, max = 40) {
  await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
  for (let i = 0; i < max; i++) { await page.keyboard.press('Tab'); await sleep(40); const t = await page.evaluate(() => { const a = document.activeElement; return (a.getAttribute('aria-label') || a.textContent || '').trim(); }); if (re.test(t)) return i + 1; }
  return null;
}
async function exercise(label, url, auth, openerRe) {
  const { ctx, page } = await open(b, url, { auth, width: 375, height: 812, dpr: 2 });
  const client = await page.createCDPSession(); await client.send('Accessibility.enable');
  const t = (out[label] = {});
  t.tabsToOpener = await tabTo(page, openerRe);
  t.openerFocus = await desc(page);
  await page.keyboard.press('Enter'); await sleep(400);
  t.opened = await dialogInfo(page); t.focusOnOpen = await desc(page);
  await page.screenshot({ path: `${SP}/shots/dialog-${label}.png` });
  const cycle = []; for (let i = 0; i < 8; i++) { await page.keyboard.press('Tab'); await sleep(50); cycle.push(await desc(page)); } t.tabCycle = cycle;
  await page.keyboard.down('Shift'); await page.keyboard.press('Tab'); await page.keyboard.up('Shift'); await sleep(50); t.shiftTab = await desc(page);
  t.backgroundClickable = await page.evaluate(() => { const l = document.querySelector('header a'); const r = l.getBoundingClientRect(); const top = document.elementFromPoint(r.left + 5, r.top + 5); return top && top !== l ? 'covered by ' + top.tagName.toLowerCase() + '.' + String(top.className).split(' ')[0] : 'NOT covered'; });
  await page.keyboard.press('Escape'); await sleep(400);
  t.afterEscape = { dialog: await dialogInfo(page), focus: await desc(page) };
  // open again, close with the first Close (X) button, the "Keep" button and an overlay click
  await page.keyboard.press('Enter'); await sleep(300);
  await page.evaluate(() => [...document.querySelectorAll('[role=dialog] button')].find((x) => /^keep/i.test(x.textContent.trim()))?.focus());
  t.keepFocus = await desc(page);
  await page.keyboard.press('Enter'); await sleep(400);
  t.afterKeep = { dialog: !!(await dialogInfo(page)), focus: await desc(page) };
  await page.keyboard.press('Enter'); await sleep(300);
  await page.mouse.click(5, 5); await sleep(400);
  t.afterOverlayClick = { dialog: !!(await dialogInfo(page)), focus: await desc(page) };
  await ctx.close();
  // 400 % zoom of a 1280x1024 window: 320x256
  const z = await open(b, url, { auth, width: 320, height: 256, dpr: 1 });
  await tabTo(z.page, openerRe); await z.page.keyboard.press('Enter'); await sleep(400);
  t.at320x256 = await dialogInfo(z.page);
  await z.page.screenshot({ path: `${SP}/shots/dialog-${label}-320x256.png` });
  const reach = await z.page.evaluate(() => [...document.querySelectorAll('[role=dialog] button')].map((x) => { const r = x.getBoundingClientRect(); return `${x.textContent.trim().slice(0, 14) || x.getAttribute('aria-label')} top=${Math.round(r.top)} bottom=${Math.round(r.bottom)}`; }));
  t.at320x256Buttons = reach;
  await z.ctx.close();
}
await exercise('cart-remove', '/cart/', true, /^Remove/);
await exercise('order-cancel', '/account/orders/EL-2026-000003/', true, /^Cancel the order/);
await b.close();
fs.writeFileSync(SP + '/a11y-dialogs.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
