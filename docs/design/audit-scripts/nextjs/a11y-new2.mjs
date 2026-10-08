import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const AXE = fs.readFileSync(SP + '/node_modules/axe-core/axe.min.js', 'utf8');
const out = {};
const b = await launch();
{
  const { ctx, page } = await open(b, '/account/security/', { auth: true }); await sleep(800);
  out.headings = await page.evaluate(() => [...document.querySelectorAll('main h1, main h2, main h3')].map((h) => `${h.tagName} ${h.textContent.trim()}`));
  out.devices = await page.evaluate(() => { const sections = [...document.querySelectorAll('main section, main [data-slot=card]')]; const d = sections.find((s) => /Log out the other|signed-in|This browser|devices/i.test(s.textContent)); return d ? { text: d.innerText.replace(/\s+/g, ' ').slice(0, 700), buttons: [...d.querySelectorAll('button')].map((x) => `${x.textContent.trim()} ${Math.round(x.getBoundingClientRect().width)}x${Math.round(x.getBoundingClientRect().height)}`), lists: [...d.querySelectorAll('ul,ol,table,dl')].map((e) => e.tagName.toLowerCase() + (e.getAttribute('aria-label') ? `[${e.getAttribute('aria-label')}]` : '')) } : 'no devices section found: ' + document.querySelector('main').innerText.replace(/\s+/g, ' ').slice(0, 1200); });
  await page.screenshot({ path: SP + '/shots/security-375.png', fullPage: true });
  await ctx.close();
}
{
  const { ctx, page } = await open(b, '/account/2fa/', { auth: true }); await sleep(800);
  await page.evaluate(() => [...document.querySelectorAll('main button')].find((e) => /Set up the authenticator app/.test(e.textContent))?.click()); await sleep(2000);
  out.qr = await page.evaluate(() => ({ imgs: [...document.querySelectorAll('main [role=img], main canvas, main svg:not([aria-hidden=true])')].map((e) => `${e.tagName.toLowerCase()} role=${e.getAttribute('role')} aria-label="${e.getAttribute('aria-label')}" ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`), keyShown: [...document.querySelectorAll('main code, main kbd, main samp, main input[readonly]')].map((e) => (e.value || e.textContent).slice(0, 6) + '…'), text: document.querySelector('main').innerText.replace(/\s+/g, ' ').slice(300, 1100), alerts: [...document.querySelectorAll('[role=alert]')].map((a) => a.textContent.trim().slice(0, 140)), url: location.pathname }));
  await page.screenshot({ path: SP + '/shots/twofa-qr.png', fullPage: true });
  await page.evaluate(AXE);
  out.qrAxe = await page.evaluate(async () => { const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } }); return { violations: r.violations.map((v) => `${v.id}(${v.nodes.length}): ${v.nodes[0].target.join(' ').slice(0, 80)}`), incomplete: r.incomplete.map((v) => `${v.id}(${v.nodes.length})`) }; });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-new2.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
