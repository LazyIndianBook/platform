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
await scenario('login-phone-empty', '/account/login/', false, [(p) => clickButton(p, '^Text me a code')]);
await scenario('login-phone-bad', '/account/login/', false, [typeInto('#phone', '123'), (p) => clickButton(p, '^Text me a code')]);
await scenario('login-email-empty', '/account/login/', false, [(p) => clickButton(p, '^Email me a code', 'main section > div > div > button, main'), (p) => sleep(400), (p) => clickButton(p, '^Email me a code', 'form')]);
await scenario('login-email-bad', '/account/login/', false, [(p) => clickButton(p, '^Email me a code'), (p) => sleep(400), typeInto('input[type=email]', 'not-an-email'), (p) => clickButton(p, '^Email me a code', 'form')]);
await scenario('login-password-empty', '/account/login/', false, [async (p) => { await p.evaluate(() => document.querySelector('details summary').click()); await sleep(300); }, (p) => clickButton(p, '^Log in$', 'details')]);
await scenario('signup-empty', '/account/signup/', false, [(p) => clickButton(p, 'register|create|sign up|continue')]);
await scenario('checkout-new-empty', '/checkout/', true, [async (p) => { await p.evaluate(() => [...document.querySelectorAll('input[type=radio]')].find((r) => /new address/i.test(r.closest('label')?.textContent || '')).click()); await sleep(300); }, (p) => clickButton(p, 'Continue to payment')]);
await scenario('contact-empty', '/contact/', false, [(p) => clickButton(p, 'send|submit|message')]);
await scenario('lookup-empty', '/orders/lookup/', false, [(p) => clickButton(p, 'find|look|show|search|check')]);
await scenario('schoolorders-empty', '/shop/school-orders/', false, [(p) => clickButton(p, 'quot|send|request|submit')]);
await scenario('coupon-empty', '/cart/', true, [(p) => clickButton(p, '^Apply')]);
await scenario('marks-empty', '/s/PHY-E02/', true, [async (p) => { await p.evaluate(() => document.querySelector('input[name=date]').value = ''); }, (p) => clickButton(p, '^Save|record|marks', '#record')]);
await scenario('marks-over', '/s/PHY-E02/', true, [typeInto('input[name=marks_obtained]', '999'), (p) => clickButton(p, '^Save|record|marks', '#record')]);
await scenario('delete-unticked', '/account/privacy/', true, [(p) => clickButton(p, 'Delete my account')]);
await scenario('address-empty', '/account/addresses/', true, [async (p) => { await p.evaluate(() => [...document.querySelectorAll('main button, main summary, main a')].find((e) => /add (a )?(new )?address|add/i.test(e.textContent))?.click()); await sleep(400); }, (p) => clickButton(p, '^Save|add address|save address')]);
await scenario('details-cleared', '/account/details/', true, [async (p) => { await p.click('input[autocomplete=name], input#full_name, input#name', { clickCount: 3 }).catch(() => {}); await p.keyboard.press('Backspace'); }, (p) => clickButton(p, '^Save')]);
await b.close();
fs.writeFileSync(SP + '/a11y-forms.json', JSON.stringify(out, null, 1));
