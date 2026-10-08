// A screenshot of one artboard of the design files (implementation/design/*.dc.html, rendered by support.js), for
// checking a page against its drawing without a browser window:
//   node scripts/design-shot.mjs "ExamLeaf A - Public.dc.html" "A Home" /tmp/home.png
import { existsSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

const [file, label, out] = process.argv.slice(2);
if (!file || !label || !out) throw new Error('usage: design-shot.mjs "<file>.dc.html" "<data-screen-label>" out.png');
const dir = path.resolve(process.env.DESIGN_DIR ?? path.resolve(import.meta.dirname, "../../implementation/design"));
const target = path.join(dir, file);
if (!existsSync(target)) throw new Error(`${target} does not exist`);

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.goto(pathToFileURL(target).href);
  await page.waitForTimeout(1500); // support.js renders the {{ }} templates
  const board = page.locator(`[data-screen-label="${label}"]`).first();
  if (!(await board.count())) {
    const labels = await page.locator("[data-screen-label]").evaluateAll((all) => all.map((el) => el.dataset.screenLabel));
    throw new Error(`no artboard "${label}" in ${file}; there are: ${labels.join(" | ")}`);
  }
  await board.scrollIntoViewIfNeeded();
  await board.screenshot({ path: out });
  console.log(`${out}: ${label} of ${file}`);
} finally {
  await browser.close();
}
