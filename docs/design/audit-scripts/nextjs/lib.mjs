import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
export const SP = process.env.REVIEW_DIR || process.cwd();
export const BASE = process.env.BASE || 'http://localhost:3003';
export const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const cookies = () => JSON.parse(fs.readFileSync(SP + '/cookies.json', 'utf8'));
export const launch = () => puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-first-run', '--no-default-browser-check', '--disable-features=Translate'] });
export async function open(browser, url, { width = 375, height = 812, dpr = 2, auth = false, reduce = false, wait = 'networkidle0' } = {}) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: dpr });
  if (reduce) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  if (auth) for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
  const errors = [];
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(`${m.type()}: ${m.text().slice(0, 200)}`); });
  page.on('pageerror', (e) => errors.push(`pageerror: ${String(e).slice(0, 200)}`));
  const resp = await page.goto(BASE + url, { waitUntil: wait, timeout: 60000 });
  return { ctx, page, errors, status: resp && resp.status() };
}
