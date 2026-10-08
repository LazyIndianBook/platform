// The Answer Script redesign's before/after set: eight pages at 1280 and 390 wide (full page, PNG). A guest cart
// is filled from the Physics product page for /cart/ and /checkout/; a temporary student (made and deleted through
// manage.py shell, so the backend's env must be set) is signed in for /account/.
//   BASE=http://localhost:3001 OUT=docs/design/screenshots/answer-script/before DJANGO_DIR=../examleaf-web \
//   DJANGO_PYTHON=../examleaf-web/.venv/bin/python node scripts/answer-script-shots.mjs   (from examleaf-frontend/)
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { chromium } from "@playwright/test";

const BASE = process.env.BASE ?? "http://localhost:3001";
const OUT = process.env.OUT ?? "screenshots";
const DJANGO_DIR = process.env.DJANGO_DIR ?? "../examleaf-web";
const PY = process.env.DJANGO_PYTHON ?? "python";
const email = `shot-${Date.now()}@example.com`;
const password = "Unusual-shot-pass-2026!";
const py = (value) => JSON.stringify(value);
const shell = (code) =>
  execFileSync(PY, ["manage.py", "shell", "-c", code], { cwd: DJANGO_DIR, stdio: "pipe" }).toString();

mkdirSync(OUT, { recursive: true });
shell(`
from datetime import date
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import User
user = User.objects.create_user(${py(email)}, ${py(password)}, full_name="Shot Student", class_level=12, date_of_birth=date(2000, 1, 1), consent_at=timezone.now())
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
`);

const PUBLIC = [
  ["home", "/"],
  ["book", "/books/physics-2027/"],
  ["solutions", "/s/PHY-E01/"],
  ["shop", "/shop/"],
  ["login", "/account/login/"],
];

async function shoot(page, name, url) {
  // a client-side redirect that is still landing aborts the first navigation: once more after it settles
  const response = await page.goto(BASE + url, { waitUntil: "networkidle" }).catch(async () => {
    await page.waitForTimeout(1500);
    return page.goto(BASE + url, { waitUntil: "networkidle" });
  });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
  const { width } = page.viewportSize();
  await page.screenshot({ path: `${OUT}/${name}-${width}.png`, fullPage: true });
  console.log(name, width, response?.status());
}

const browser = await chromium.launch();
try {
  for (const [width, height] of [
    [1280, 800],
    [390, 844],
  ]) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: width < 600 ? 2 : 1 });
    const page = await context.newPage();
    for (const [name, url] of PUBLIC) await shoot(page, name, url);
    await page.goto(BASE + "/shop/physics-sample-papers-2027/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Add to cart" }).click();
    await page.waitForTimeout(1500);
    await shoot(page, "cart", "/cart/");
    await shoot(page, "checkout", "/checkout/");
    await page.goto(BASE + "/account/login/?next=/account/", { waitUntil: "networkidle" });
    await page.getByText("Log in with email and password").click();
    await page.locator("#login").fill(email);
    await page.locator("#password").fill(password);
    await page.locator("details form").getByRole("button", { name: "Log in" }).click();
    await page.waitForURL(/\/account\/$/, { timeout: 30_000 });
    await shoot(page, "account", "/account/");
    await context.close();
  }
} finally {
  await browser.close();
  shell(`from accounts.models import User; print(User.objects.filter(email=${py(email)}).delete())`);
}
