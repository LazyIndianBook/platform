// The header's menu drawer at 375 and 320 px, with real key presses.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
import { focusInfo } from './inpage.mjs';
const out = {};
const b = await launch();
async function ax(client) {
  const { result } = await client.send('Runtime.evaluate', { expression: 'document.activeElement' });
  if (!result.objectId) return {};
  const { nodes } = await client.send('Accessibility.getPartialAXTree', { objectId: result.objectId, fetchRelatives: false });
  const n = nodes[0] || {}; const props = Object.fromEntries((n.properties || []).map((p) => [p.name, p.value && p.value.value]));
  return { role: n.role && n.role.value, name: n.name && n.name.value, expanded: props.expanded, controls: props.controls };
}
const state = (page) => page.evaluate(() => {
  const t = document.querySelector('button[aria-controls=site-menu]'); const m = document.getElementById('site-menu');
  const r = m.getBoundingClientRect(); const tr = t.getBoundingClientRect();
  return { expanded: t.getAttribute('aria-expanded'), label: t.textContent.trim(), menuDisplay: getComputedStyle(m).display, menuTop: Math.round(r.top), menuBottom: Math.round(r.bottom), toggleY: Math.round(tr.top), active: document.activeElement.tagName.toLowerCase() + (document.activeElement.getAttribute('aria-controls') ? '[controls]' : '') + ' "' + (document.activeElement.textContent || '').trim().slice(0, 24) + '"' };
});
const short = (page) => page.evaluate(() => { const a = document.activeElement; const r = a.getBoundingClientRect(); return `${a.tagName.toLowerCase()} "${(a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 28)}" y=${Math.round(r.top)} inMenu=${!!a.closest('#site-menu')}`; });
for (const w of [375, 320]) {
  const { ctx, page } = await open(b, '/', { width: w, height: 812, dpr: 2 });
  const client = await page.createCDPSession(); await client.send('Accessibility.enable');
  const t = (out['w' + w] = {});
  await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
  t.before = await state(page);
  for (let i = 0; i < 6; i++) { await page.keyboard.press('Tab'); await sleep(60); if (await page.evaluate(() => document.activeElement.matches('button[aria-controls=site-menu]'))) { t.tabsToMenu = i + 1; break; } }
  t.toggleAx = await ax(client);
  t.toggleRing = await page.evaluate(focusInfo).then((f) => ({ indicator: f.indicator, outline: f.outline, contrast: f.ringContrast, rect: f.rect }));
  await page.keyboard.press('Enter'); await sleep(200); t.afterEnter = await state(page); t.axAfterEnter = await ax(client);
  await page.screenshot({ path: `${SP}/shots/menu-open-${w}.png`, clip: { x: 0, y: 0, width: w, height: 520 } });
  const forward = []; for (let i = 0; i < 6; i++) { await page.keyboard.press('Tab'); await sleep(80); forward.push(await short(page)); } t.tabForwardFromToggleWhileOpen = forward;
  // back to the toggle, then Shift+Tab
  await page.evaluate(() => document.querySelector('button[aria-controls=site-menu]').focus());
  const back = []; for (let i = 0; i < 5; i++) { await page.keyboard.down('Shift'); await page.keyboard.press('Tab'); await page.keyboard.up('Shift'); await sleep(80); back.push(await short(page)); } t.shiftTabFromToggleWhileOpen = back;
  // Escape from a link inside the menu
  await page.evaluate(() => document.querySelector('#site-menu a').focus());
  await page.keyboard.press('Escape'); await sleep(150); t.afterEscapeFromMenuLink = await state(page);
  // reopen; Escape from the toggle; Space; outside click
  await page.keyboard.press('Space'); await sleep(150); t.afterSpace = await state(page);
  await page.keyboard.press('Escape'); await sleep(150); t.afterEscapeOnToggle = await state(page);
  await page.click('button[aria-controls=site-menu]'); await sleep(150); t.afterClick = await state(page);
  await page.mouse.click(10, 700); await sleep(150); t.afterOutsideClick = await state(page);
  // a link in the menu: navigates and the menu is shut on the new page
  await page.click('button[aria-controls=site-menu]'); await sleep(150);
  await page.evaluate(() => [...document.querySelectorAll('#site-menu a')].find((a) => /shop/i.test(a.textContent)).click()); await sleep(1200);
  t.afterNavigation = await state(page).catch((e) => String(e)); t.urlAfterNavigation = page.url().replace('http://localhost:3003', '');
  t.focusAfterNavigation = await short(page);
  await ctx.close();
}
// signed in: the menu has a button (Log out) inside the nav
{
  const { ctx, page } = await open(b, '/', { width: 375, height: 812, dpr: 2, auth: true });
  await page.click('button[aria-controls=site-menu]'); await sleep(150);
  out.signedInMenu = await page.evaluate(() => [...document.querySelectorAll('#site-menu > *')].map((e) => `${e.tagName.toLowerCase()} "${e.textContent.trim()}" ${e.getAttribute('aria-current') || ''}`));
  await page.screenshot({ path: `${SP}/shots/menu-open-signedin-375.png`, clip: { x: 0, y: 0, width: 375, height: 420 } });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-menu.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
