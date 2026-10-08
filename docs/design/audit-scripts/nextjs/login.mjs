// node login.mjs  -> signs in through the frontend's email-code flow and saves the cookies to cookies.json
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const SP = process.env.REVIEW_DIR || process.cwd();
const BASE = 'http://localhost:3003';
const EMAIL = 'nx-review-temp@example.com';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function emailedCode(after, timeout = 30000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const text = fs.readFileSync(SP + '/django.log', 'utf8');
    const start = text.lastIndexOf(`To: ${EMAIL}`);
    if (start >= after && start !== -1) { const m = /^(\d{6})\r?$/m.exec(text.slice(start)); if (m) return m[1]; }
    await sleep(250);
  }
  throw new Error('no code');
}
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-first-run'] });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 });
page.on('console', (m) => console.log('console', m.type(), m.text().slice(0, 200)));
await page.goto(BASE + '/account/login/', { waitUntil: 'networkidle0' });
const after = fs.readFileSync(SP + '/django.log', 'utf8').length;
for (const b of await page.$$('button')) { const t = await b.evaluate((e) => e.textContent); if (/Email me a code/.test(t)) { await b.click(); break; } }
await sleep(600);
await page.type('input[type=email]', EMAIL);
await page.keyboard.press('Enter');
const code = await emailedCode(after);
console.log('code found');
await sleep(500);
await page.screenshot({ path: SP + '/shots/login-code.png' });
console.log((await page.evaluate(() => document.querySelector('main').innerText)).slice(0, 300));
await page.keyboard.type(code);
await sleep(500);
await page.screenshot({ path: SP + '/shots/login-typed.png' });
await page.keyboard.press('Enter');
await sleep(4000);
console.log('url', page.url());
await page.screenshot({ path: SP + '/shots/login-done.png' });
const cookies = await page.cookies();
fs.writeFileSync(SP + '/cookies.json', JSON.stringify(cookies, null, 1));
console.log(cookies.map((c) => `${c.name} httpOnly=${c.httpOnly} sameSite=${c.sameSite} secure=${c.secure} path=${c.path} exp=${c.expires}`).join('\n'));
await browser.close();
