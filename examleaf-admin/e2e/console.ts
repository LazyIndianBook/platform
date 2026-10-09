// The browser's side of the console's tests: signing in as a staff member (password, then the authenticator's code)
// and an accessibility check with axe-core (the public site's approach: its axe.min.js evaluated in the page, WCAG 2.0
// to 2.2 A and AA plus best practice; the Next.js development overlay is left out).
import { readFileSync } from "node:fs";

import { expect, type Page } from "@playwright/test";

import { freshCode, type Staff } from "./django";

const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

/** Signs in from /sign-in/ and lands on `next`; answers the code it used (each code works once). */
export async function signIn(page: Page, staff: Staff, next = "/", used: string | null = null): Promise<string> {
  await page.goto(`/sign-in/?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email address").fill(staff.email);
  await page.locator("#password").fill(staff.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Two-step check" })).toBeVisible();
  const code = await freshCode(staff.secret, used);
  await page.getByRole("textbox", { name: "6-digit code" }).fill(code);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL((url) => url.pathname === next.split("?")[0]);
  return code;
}

export type AxeResult = { violations: string[] };

/** axe-core's violations on the page as it stands, one line each (after any running animation has ended: a dialog
 *  fading in would read as low contrast). */
export async function axe(page: Page): Promise<AxeResult> {
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

/** A toast with these words, in the messages region (polite, announced once). */
export const toast = (page: Page, words: string) =>
  page.getByRole("region", { name: "Messages" }).getByText(words, { exact: true });
