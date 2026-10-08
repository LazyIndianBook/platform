// Error identification after an invalid submit, form by form (nothing valid is ever submitted: no account, order or request is made).
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const out = {};
const b = await launch();
const probe = (page) => page.evaluate(() => {
  const txt = (e, n = 90) => (e ? e.textContent.replace(/\s+/g, ' ').trim().slice(0, n) : null);
  const sel = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.getAttribute('name') ? `[name=${e.getAttribute('name')}]` : '') + (e.type && e.tagName === 'INPUT' ? `[${e.type}]` : '');
  const alerts = [...document.querySelectorAll('[role=alert]')].map((a) => ({ text: txt(a, 160), hasLinks: a.querySelectorAll('a').length }));
  const summaryEl = [...document.querySelectorAll('[role=alert]')].find((a) => /There is a problem/.test(a.textContent));
  const wrapper = summaryEl && summaryEl.parentElement;
  const summary = summaryEl ? {
    role: summaryEl.getAttribute('role'), focused: wrapper === document.activeElement || summaryEl.contains(document.activeElement), wrapperTabindex: wrapper.getAttribute('tabindex'),
    wrapperOutline: getComputedStyle(wrapper).outlineStyle + ' ' + getComputedStyle(wrapper).outlineWidth,
    links: [...summaryEl.querySelectorAll('a[href^="#"]')].map((a) => { const id = decodeURIComponent(a.getAttribute('href').slice(1)); const t = document.getElementById(id); const label = t && ((t.labels && t.labels[0]) ? txt(t.labels[0], 40) : t.getAttribute('aria-label')); return { text: txt(a, 80), href: a.getAttribute('href'), resolves: !!t, target: t ? sel(t) : null, targetLabel: label, targetIsControl: !!t && /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(t.tagName) }; }),
  } : null;
  const invalid = [...document.querySelectorAll('[aria-invalid="true"]')].map((e) => {
    const ids = (e.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    const lab = e.labels && e.labels[0] ? txt(e.labels[0], 50) : (e.getAttribute('aria-label') || null);
    return { control: sel(e), label: lab, required: e.required || e.getAttribute('aria-required') === 'true', describedby: ids, resolves: ids.map((id) => !!document.getElementById(id)), described: ids.map((id) => txt(document.getElementById(id), 70)) };
  });
  const orphanErrors = [...document.querySelectorAll('[data-slot=field-error]')].filter((e) => !(e.id && document.querySelector(`[aria-describedby~="${e.id}"]`))).map((e) => ({ id: e.id, text: txt(e, 80) }));
  const nativeBubbles = [...document.querySelectorAll('input:invalid,select:invalid,textarea:invalid')].length;
  return { alerts, summary, invalid, orphanErrors, activeElement: document.activeElement.tagName.toLowerCase() + (document.activeElement.id ? '#' + document.activeElement.id : ''), formsNoValidate: [...document.forms].map((f) => f.noValidate) , nativeInvalidCount: nativeBubbles };
});
const clickButton = async (page, re, scope = 'main') => {
  const h = await page.evaluateHandle((re, scope) => [...document.querySelectorAll(`${scope} button, ${scope} [type=submit]`)].find((e) => new RegExp(re, 'i').test((e.getAttribute('aria-label') || e.textContent).trim()) && e.getBoundingClientRect().width > 0), re, scope);
  const el = h.asElement(); if (!el) throw new Error('no button ' + re);
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' })); await sleep(150); await el.click();
};
async function scenario(label, url, auth, steps, { width = 375 } = {}) {
  const { ctx, page } = await open(b, url, { auth, width, height: 812, dpr: 2 });
  await sleep(500);
  try {
    for (const s of steps) await s(page);
    await sleep(1000);
    out[label] = await probe(page);
    // click the first summary link (if any) and see where focus goes
    const first = out[label].summary && out[label].summary.links[0];
    if (first) {
      await page.evaluate((h) => document.querySelector(`a[href="${h}"]`)?.click(), first.href); await sleep(300);
      out[label].afterFirstSummaryLink = await page.evaluate(() => { const a = document.activeElement; return `${a.tagName.toLowerCase()}${a.id ? '#' + a.id : ''}`; });
    }
    await page.screenshot({ path: `${SP}/shots/err-${label}.png`, fullPage: false });
    console.log(label.padEnd(18), 'summary', out[label].summary ? `focused=${out[label].summary.focused} links=${out[label].summary.links.length}` : 'none', '| invalid', out[label].invalid.length, '| orphan', out[label].orphanErrors.length, '| alerts', out[label].alerts.length);
  } catch (e) { out[label] = { error: String(e).slice(0, 200) }; console.log(label, 'ERROR', String(e).slice(0, 160)); }
  await ctx.close();
}
const typeInto = (sel, text) => async (p) => { await p.click(sel); await p.keyboard.type(text, { delay: 15 }); };
await scenario('lookup-empty', '/orders/lookup/', false, [(p) => clickButton(p, 'Email me the link')]);
await scenario('address-empty', '/account/addresses/', true, [async (p) => { await p.evaluate(() => [...document.querySelectorAll('main button')].find((e) => /Add an address/.test(e.textContent))?.click()); await sleep(500); }, async (p) => { await p.screenshot({ path: SP + '/shots/addr-open.png' }); await p.evaluate(() => { window.__btns = [...document.querySelectorAll('main button, main [type=submit]')].map((e) => e.textContent.trim()); }); console.log('address buttons', await p.evaluate(() => window.__btns)); }, (p) => clickButton(p, '^(Save|Add|Save address|Add address)$')]);
await scenario('details-cleared', '/account/details/', true, [async (p) => { await p.click('#full_name', { clickCount: 3 }); await p.keyboard.press('Backspace'); }, (p) => clickButton(p, 'Save my details')]);
await scenario('teacher-empty', '/account/teacher/', true, [(p) => clickButton(p, '^Send')]);
await scenario('security-password-mismatch', '/account/security/', true, [typeInto('#new_password', 'abcdefghij1'), typeInto('#new_password2', 'zzzzzzzzzz9'), (p) => clickButton(p, 'Set my password')]);
await scenario('security-phone-bad', '/account/security/', true, [typeInto('#phone', '12'), (p) => clickButton(p, 'Text me a code')]);
await scenario('security-email-bad', '/account/security/', true, [typeInto('#email', 'nope'), (p) => clickButton(p, 'Email me a code')]);
await b.close();
fs.writeFileSync(SP + '/a11y-forms2.json', JSON.stringify(out, null, 1));
