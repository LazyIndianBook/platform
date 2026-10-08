// Address form errors, and the OTP input: structure, keyboard, wrong code.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
import { focusInfo } from './inpage.mjs';
const out = {};
const b = await launch();
// --- the address form
{
  const { ctx, page } = await open(b, '/account/addresses/', { auth: true });
  await sleep(300);
  await page.evaluate(() => [...document.querySelectorAll('main button')].find((e) => /Add an address/.test(e.textContent))?.click()); await sleep(500);
  out.addressOpenFocus = await page.evaluate(() => `${document.activeElement.tagName.toLowerCase()}#${document.activeElement.id}`);
  await page.evaluate(() => [...document.querySelectorAll('main button')].find((e) => /Save the address/.test(e.textContent))?.click()); await sleep(1000);
  out.address = await page.evaluate(() => ({ summary: [...document.querySelectorAll('[role=alert]')].map((a) => a.textContent.trim().slice(0, 300)), links: [...document.querySelectorAll('[role=alert] a')].map((a) => `${a.textContent} -> ${a.getAttribute('href')} resolves=${!!document.getElementById(a.getAttribute('href').slice(1))}`), invalid: [...document.querySelectorAll('[aria-invalid=true]')].map((e) => e.id), active: document.activeElement.tagName + '#' + document.activeElement.id }));
  await ctx.close();
}
// --- the OTP step: ask for an emailed code (to the temporary student), look at the input, try a wrong code
{
  const { ctx, page } = await open(b, '/account/login/', { auth: false });
  const client = await page.createCDPSession(); await client.send('Accessibility.enable');
  await sleep(400);
  await page.evaluate(() => [...document.querySelectorAll('button')].find((e) => /^Email me a code/.test(e.textContent.trim()))?.click()); await sleep(500);
  await page.type('input[type=email]', 'nx-review-temp@example.com'); await page.keyboard.press('Enter');
  await page.waitForSelector('input[autocomplete=one-time-code]', { timeout: 30000 });
  await sleep(600);
  out.otp = await page.evaluate(() => {
    const i = document.querySelector('input[autocomplete=one-time-code]'); const r = i.getBoundingClientRect(); const cs = getComputedStyle(i);
    const label = i.labels && i.labels[0] ? i.labels[0].textContent.trim() : null;
    return { attrs: Object.fromEntries([...i.attributes].map((a) => [a.name, a.value.slice(0, 60)])), label, rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, opacity: cs.opacity, caretColor: cs.caretColor, active: document.activeElement === i, containerHtml: i.parentElement.outerHTML.replace(/\s+/g, ' ').slice(0, 500), slotTexts: [...i.parentElement.querySelectorAll('div')].map((d) => d.textContent).slice(0, 8), ariaHiddenSlots: [...i.parentElement.querySelectorAll('div')].filter((d) => d.getAttribute('aria-hidden') === 'true').length };
  });
  const { result } = await client.send('Runtime.evaluate', { expression: 'document.querySelector("input[autocomplete=one-time-code]")' });
  const ax = await client.send('Accessibility.getPartialAXTree', { objectId: result.objectId, fetchRelatives: true });
  out.otpAx = ax.nodes.slice(0, 6).map((n) => `${n.role && n.role.value} "${n.name && n.name.value}" ignored=${n.ignored}`);
  out.otpFocusRing = await page.evaluate(focusInfo).then((f) => ({ sel: f.sel, indicator: f.indicator, outline: f.outline, wrapperRing: f.wrapperRing, contrast: f.ringContrast }));
  await page.screenshot({ path: SP + '/shots/otp-step.png' });
  await page.keyboard.type('12345'); await sleep(200);
  out.afterFive = await page.evaluate(() => ({ value: document.querySelector('input[autocomplete=one-time-code]').value, buttonDisabled: [...document.querySelectorAll('main button')].find((e) => /^Log in$/.test(e.textContent.trim())).disabled, activeSlots: [...document.querySelectorAll('[data-active]')].length }));
  await page.keyboard.press('Backspace'); await sleep(100);
  out.afterBackspace = await page.evaluate(() => document.querySelector('input[autocomplete=one-time-code]').value);
  await page.keyboard.type('00'); await sleep(200);
  out.afterSix = await page.evaluate(() => ({ value: document.querySelector('input[autocomplete=one-time-code]').value, buttonDisabled: [...document.querySelectorAll('main button')].find((e) => /^Log in$/.test(e.textContent.trim())).disabled }));
  // wrong code: 000000 can still be right by chance (1 in a million); accept
  await page.keyboard.press('Enter'); await sleep(2000);
  out.wrongCode = await page.evaluate(() => ({ summary: [...document.querySelectorAll('[role=alert]')].map((a) => a.textContent.trim().slice(0, 200)), links: [...document.querySelectorAll('[role=alert] a')].map((a) => `${a.textContent} -> ${a.getAttribute('href')} resolves=${!!document.getElementById(a.getAttribute('href').slice(1))}`), invalidInput: document.querySelector('input[autocomplete=one-time-code]').getAttribute('aria-invalid'), describedby: document.querySelector('input[autocomplete=one-time-code]').getAttribute('aria-describedby'), active: document.activeElement.tagName + '#' + document.activeElement.id, slotsRed: [...document.querySelectorAll('input[autocomplete=one-time-code]')[0].parentElement.querySelectorAll('div')].filter((d) => getComputedStyle(d).borderColor.includes('rgb(')).length }));
  await page.screenshot({ path: SP + '/shots/otp-wrong.png' });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-otp.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
