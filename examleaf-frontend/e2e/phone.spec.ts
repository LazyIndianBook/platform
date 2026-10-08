// The home page and a paper on a phone (Pixel 7, 412 px): one header row with Menu, the drawer, no sideways scroll.
import { expect, test } from "@playwright/test";

test("the header keeps one row and Menu opens the links as a drawer", async ({ page }) => {
  await page.goto("/");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
  await menu.click();
  await expect(page.getByRole("button", { name: "Close" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Shop" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Menu" })).toBeFocused();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("a paper's solutions fit the phone", async ({ page }) => {
  await page.goto("/s/PHY-E01/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the home page and the shop fit 320 to 414 px, and Tab goes from Menu into the open menu", async ({ page }) => {
  for (const width of [320, 360, 375, 414]) {
    await page.setViewportSize({ width, height: 800 });
    for (const path of ["/", "/shop/"]) {
      await page.goto(path);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${path} at ${width} px`).toBeLessThanOrEqual(0); // accessibility review F2, F5
    }
  }
  await page.getByRole("button", { name: "Menu" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Books" })).toBeFocused(); // F3: the first link
});
