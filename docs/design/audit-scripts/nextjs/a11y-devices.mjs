import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const AXE = fs.readFileSync(SP + '/node_modules/axe-core/axe.min.js', 'utf8');
const b = await launch();
const { ctx, page } = await open(b, '/account/security/', { auth: true }); await sleep(700);
const info = await page.evaluate(() => { const h = [...document.querySelectorAll('main h2')].find((e) => /Where you are logged in/.test(e.textContent)); const card = h.closest('[data-slot=card], section') || h.parentElement.parentElement; const lis = [...card.querySelectorAll('li')]; return { rows: lis.map((l) => l.innerText.replace(/\s+/g, ' ')), buttons: [...card.querySelectorAll('button')].map((x) => `${x.textContent.trim()} ${Math.round(x.getBoundingClientRect().width)}x${Math.round(x.getBoundingClientRect().height)}`), listRole: card.querySelector('ul')?.getAttribute('role'), listLabel: card.querySelector('ul')?.getAttribute('aria-label') }; });
console.log(JSON.stringify(info, null, 1));
await page.evaluate(AXE);
console.log(JSON.stringify(await page.evaluate(async () => { const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } }); return r.violations.map((v) => `${v.id}(${v.nodes.length})`); })));
await page.screenshot({ path: SP + '/shots/devices-375.png', fullPage: false, clip: { x: 0, y: 0, width: 375, height: 812 } });
// where does the button sit, keyboard: tab to it
await b.close();
