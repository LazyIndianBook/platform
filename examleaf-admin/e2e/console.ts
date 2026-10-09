// The browser's side of the console's tests: signing in as a staff member (password, then the authenticator's code),
// answering "confirm it's you" when a sensitive action asks, and an accessibility check with axe-core (the public
// site's approach: its axe.min.js evaluated in the page, WCAG 2.0 to 2.2 A and AA plus best practice; the Next.js
// development overlay is left out).
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page } from "@playwright/test";

import { freshCode, type Staff } from "./django";

const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

/** The authenticator codes a test has used: each works once (allauth marks it used for its 30 s). */
export type Codes = { last: string | null };

/** Signs in from /sign-in/ and lands on `next`; keeps the code it used. */
export async function signIn(page: Page, staff: Staff, next = "/", codes: Codes = { last: null }): Promise<string> {
  await page.goto(`/sign-in/?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email address").fill(staff.email);
  await page.locator("#password").fill(staff.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Two-step check" })).toBeVisible();
  const code = await freshCode(staff.secret, codes.last);
  codes.last = code;
  await page.getByRole("textbox", { name: "6-digit code" }).fill(code);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL((url) => url.pathname === next.split(/[?#]/)[0]);
  return code;
}

/** Waits for what an action shows when it worked (`done`); when "Confirm it's you" asks first (a re-authentication
 *  older than 5 minutes), answers it with a fresh code, and the call goes through. */
export async function settle(page: Page, done: Locator, staff: Staff, codes: Codes) {
  const confirm = page.getByRole("dialog", { name: "Confirm it's you" });
  await expect(done.or(confirm).first()).toBeVisible();
  if (await confirm.isVisible()) {
    const code = await freshCode(staff.secret, codes.last);
    codes.last = code;
    await confirm.getByRole("textbox", { name: "6-digit code" }).fill(code);
    await confirm.getByRole("button", { name: "Confirm" }).click();
    await expect(done.first()).toBeVisible();
  }
}

export type AxeResult = { violations: string[] };

/** axe-core's violations on the page as it stands, one line each (once it has loaded, and after any running animation
 *  has ended: a dialog fading in would read as low contrast). A development server that has just compiled the page
 *  may reload it, more than once on a cold start: then axe runs again on the page it reloaded to. */
export async function axe(page: Page, tries = 3): Promise<AxeResult> {
  await page.waitForLoadState("load");
  await page.waitForLoadState("networkidle");
  try {
    return await runAxe(page);
  } catch (error) {
    if (tries <= 1 || !String(error).includes("Execution context was destroyed")) throw error;
    return axe(page, tries - 1);
  }
}

async function runAxe(page: Page): Promise<AxeResult> {
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
  await page.evaluate(AXE);
  return page.evaluate(async () => {
    const run = (window as unknown as { axe: { run: (context: unknown, options: unknown) => Promise<unknown> } }).axe
      .run;
    const result = (await run(
      { exclude: [["nextjs-portal"]] },
      { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } },
    )) as { violations: { id: string; nodes: { target: string[] }[] }[] };
    return {
      violations: result.violations.map(
        (violation) => `${violation.id} (${violation.nodes.length}): ${violation.nodes[0]?.target.join(" ")}`,
      ),
    };
  });
}

/** How wide the page is: wider than the window means it scrolls sideways. */
export const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);

/** Every page: axe at its width, no sideways scroll, and at 320 px too on a phone's width. */
export async function checkPages(page: Page, paths: string[], width: number) {
  const viewport = page.viewportSize()!;
  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
    expect.soft((await axe(page)).violations, `axe on ${path}`).toEqual([]);
    expect.soft(await pageWidth(page), `${path} is wider than ${width}`).toBeLessThanOrEqual(width);
    if (width < 900) {
      await page.setViewportSize({ width: 320, height: 640 });
      expect.soft(await pageWidth(page), `${path} is wider than 320`).toBeLessThanOrEqual(320);
      await page.setViewportSize(viewport);
    }
  }
}

/** A toast with these words, in the messages region (polite, announced once). */
export const toast = (page: Page, words: string) =>
  page.getByRole("region", { name: "Messages" }).getByText(words, { exact: true });

/** The CSRF token the browser holds, for an API call made from the test. */
export async function csrf(page: Page): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  return { "X-CSRFToken": cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? "" };
}
