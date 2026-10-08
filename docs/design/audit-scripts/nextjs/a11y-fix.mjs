// The review's keyboard findings, again, with real key presses (headless Chrome): F3 menu order, F1 stepper focus,
// F6 dialog focus return, F4 the toast after add to cart.
import { launch, open, sleep } from './lib.mjs';
const browser = await launch();
const name = (page) => page.evaluate(() => { const e = document.activeElement; return `${e.tagName.toLowerCase()} "${(e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 50)}"`; });

{ // F3
  const { page } = await open(browser, '/');
  for (let i = 0; i < 6; i++) { await page.keyboard.press('Tab'); if ((await name(page)).includes('Menu')) break; }
  console.log('F3 on', await name(page));
  await page.keyboard.press('Enter'); await sleep(200);
  await page.keyboard.press('Tab');
  console.log('F3 after Tab from the open menu:', await name(page));
}
{ // F1 + F6
  const { page } = await open(browser, '/cart/', { auth: true });
  const more = await page.$('button[aria-label^="One copy more"]');
  await more.focus();
  const value = () => page.$eval('input[type=number]', (e) => e.value);
  console.log('F1 copies', await value(), 'focus', await name(page));
  await page.keyboard.press('Enter'); await sleep(1500);
  console.log('F1 after Enter: copies', await value(), 'focus', await name(page));
  await page.keyboard.press('Enter'); await sleep(1500);
  console.log('F1 after a second Enter: copies', await value(), 'focus', await name(page));
  const less = await page.$('button[aria-label^="One copy fewer"]');
  await less.focus(); await page.keyboard.press('Enter'); await sleep(1200); await page.keyboard.press('Enter'); await sleep(1200);
  console.log('F1 back down: copies', await value());
  const remove = (await page.$$('button')).find(async (b) => (await b.evaluate((e) => e.textContent)) === 'Remove');
  for (const b of await page.$$('button')) if ((await b.evaluate((e) => e.textContent.trim())) === 'Remove') { await b.focus(); break; }
  await page.keyboard.press('Enter'); await sleep(300);
  console.log('F6 dialog open, focus', await name(page));
  await page.keyboard.press('Escape'); await sleep(300);
  console.log('F6 after Escape, focus', await name(page));
}
{ // F4
  const { page } = await open(browser, '/shop/physics-sample-papers-2027/', { auth: true });
  for (const b of await page.$$('button')) if (/Add to cart/i.test(await b.evaluate((e) => e.textContent))) { await b.click(); break; }
  await sleep(2500);
  console.log('F4 2.5 s later on', new URL(page.url()).pathname, 'toast:', await page.evaluate(() => [...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')));
  await sleep(4500);
  console.log('F4 7 s later toast count:', await page.evaluate(() => document.querySelectorAll('[data-toast]').length));
}
await browser.close();
