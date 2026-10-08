// The revision course's pages on the website (proposed; ExamLeaf A - Learning (LMS)), only while the backend's config/
// has web_course on (WEB_COURSE=1): skipped otherwise, as on the shared e2e backend. A temporary student open to
// Physics (made and deleted through manage.py shell; the email starts with e-course-) and a Physics chapter made for
// the test: three clips (no files: nothing plays), two flash cards, a fill-in-the-blank and a multiple-choice question.
import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { djangoEnv } from "../playwright.config";
import { createStudent } from "./account-django";

const API = `http://localhost:${process.env.E2E_API_PORT ?? "8100"}`;
const stamp = Date.now();
const email = `e-course-${stamp}@example.com`;
const password = "Unusual-e-course-pass-2026!";
const title = `e-course-${stamp}`;
let chapter = 0; // the test chapter's number among Physics' chapters

function shell(code: string): string {
  const dir = path.resolve(__dirname, "../../examleaf-web");
  const python = process.env.DJANGO_PYTHON ?? path.join(dir, ".venv/bin/python");
  return execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: dir,
    env: { ...process.env, ...djangoEnv },
    stdio: "pipe",
  }).toString();
}

test.describe.configure({ mode: "serial", timeout: 120_000 }); // generous for a dev server too
test.beforeAll(async () => {
  const config = await (await fetch(`${API}/api/v1/config/`)).json();
  test.skip(!config.web_course, "config/ web_course is off: the course has no pages on the website");
  createStudent(email, password);
  chapter = Number(
    shell(`
from datetime import date, timedelta
from django.db.models import Max
from django.utils import timezone
from accounts.models import User
from content.models import Subject
from learn.models import Chapter, Clip, Entitlement, FlashCard, Learner, Progress, QuizItem, Revision
user, subject, title = User.objects.get(email=${JSON.stringify(email)}), Subject.objects.get(code="PHY"), ${JSON.stringify(title)}
number = (Chapter.objects.filter(subject=subject).aggregate(n=Max("number"))["n"] or 0) + 1
chapter = Chapter.objects.create(subject=subject, number=number, title=title, weight=7, frequency=16, must_do="Wheatstone bridge numericals")
revision = Revision.objects.create(chapter=chapter, title=f"Revise {title}", status="published")
clips = [Clip.objects.create(revision=revision, order=i, title=f"{title}: clip {i}", processing="ready", duration=120, notes="Going round a loop, the sum of the potential differences is zero.", hls_path=f"learn/hls/{title}-{i}/v1/master.m3u8") for i in (1, 2, 3)]
Progress.objects.create(user=user, clip=clips[0], seconds_watched=120, completed=True)
Entitlement.objects.create(user=user, subject=subject, valid_until=timezone.localdate() + timedelta(days=365))
Learner.objects.create(user=user, exam_date=date.today() + timedelta(days=120), minutes_per_day=30)
FlashCard.objects.create(chapter=chapter, order=1, front="SI unit of resistivity?", back="Ohm metre")
FlashCard.objects.create(chapter=chapter, order=2, front="A balanced bridge?", back="P/Q = R/S")
QuizItem.objects.create(chapter=chapter, kind="fill_blank", text="In a balanced Wheatstone bridge, the galvanometer's current is ______.", answer="zero|0", explanation="Its two ends are at the same potential.")
QuizItem.objects.create(chapter=chapter, kind="mcq", text="The SI unit of resistivity is", options=["(i) ohm", "(ii) ohm metre"], answer="2")
print(number)
`)
      .trim()
      .split("\n")
      .at(-1),
  );
});
test.afterAll(() => {
  if (!chapter) return;
  shell(`
from accounts.models import User
from learn.models import Chapter
print(User.objects.filter(email=${JSON.stringify(email)}, is_staff=False).delete(), Chapter.objects.filter(title=${JSON.stringify(title)}).delete())
`);
});

async function logIn(page: Page, next: string) {
  await page.goto(`/account/login/?next=${encodeURIComponent(next)}`, { waitUntil: "networkidle" });
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(new RegExp(`${next.replace(/\?/g, "\\?")}$`), { timeout: 60_000 });
  await page.waitForLoadState("networkidle"); // the page's script is in (its keys and buttons answer)
}

test("a chapter: its clips as the API marks them, the clip's notes, the cards and the quiz", async ({ page }) => {
  const path = `/revision/physics/${chapter}/`;
  await logIn(page, path);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.getByText("3 clips · 6 min · 1 of 3 watched")).toBeVisible();
  const clips = page.getByRole("list", { name: "Clips" });
  await expect(clips.getByRole("link", { name: /clip 1 \(watched\)/ })).toBeVisible();
  await expect(clips.getByRole("link", { name: /Playing: .*clip 2/ })).toHaveAttribute("aria-current", "true");
  await expect(page.getByText("Going round a loop, the sum of the potential differences is zero.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Flash cards\s+2 cards/ })).toHaveAttribute("href", `${path}cards/`);
  await expect(page.getByRole("link", { name: /Quiz\s+2 one-mark questions/ })).toHaveAttribute("href", `${path}quiz/`);
  expect((await page.request.get("/revision/physics/9999/")).status()).toBe(404);
});

test("the quiz: no verdict before the server answers, one answer however often Check is pressed", async ({ page }) => {
  await logIn(page, `/revision/physics/${chapter}/quiz/`);
  let sent = 0;
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/v1/learn/quiz/*/attempt/", async (route) => {
    sent += 1;
    await held;
    await route.continue();
  });
  await page.getByLabel("Your answer").fill("maximum");
  const check = page.getByRole("button", { name: "Check" });
  await check.click();
  await expect(check).toHaveAttribute("aria-busy", "true");
  await check.click({ force: true });
  await page.getByLabel("Your answer").press("Enter");
  await expect(page.getByText(/NOT QUITE|RIGHT/)).toHaveCount(0);
  release();
  await expect(page.getByRole("status").filter({ hasText: "NOT QUITE" })).toContainText("ANSWER: Zero");
  await expect(page.getByText("Its two ends are at the same potential.")).toBeVisible();
  expect(sent).toBe(1);
  await page.unroute("**/api/v1/learn/quiz/*/attempt/");

  await page.getByRole("button", { name: "Next question" }).click();
  await page.getByRole("radio", { name: "(ii) ohm metre" }).check();
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByRole("status").filter({ hasText: "RIGHT" })).toBeVisible();
  await page.getByRole("button", { name: "See your result" }).click();
  await expect(page.getByRole("heading", { name: "1 of 2 right" })).toBeVisible();
  await expect(page.getByText("The one you missed comes back in Revise again tomorrow.")).toBeVisible();
});

test("flash cards: Space turns a card, 1 and 2 answer it, one review each", async ({ page }) => {
  await logIn(page, `/revision/physics/${chapter}/cards/`);
  const reviews: unknown[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/review/")) reviews.push(request.postDataJSON());
  });
  await expect(page.getByText("SI unit of resistivity?")).toBeVisible();
  await page.keyboard.press("Space");
  await expect(page.getByText("Ohm metre")).toBeVisible();
  await page.keyboard.press("2");
  await expect(page.getByText("A balanced bridge?")).toBeVisible();
  await page.keyboard.press("Space");
  await page.keyboard.press("1");
  await expect(page.getByRole("heading", { name: "You knew 1 of 2" })).toBeVisible();
  expect(reviews).toEqual([{ known: true }, { known: false }]);
});

test("course settings: the API's words for minutes outside 10 to 300", async ({ page }) => {
  await logIn(page, "/account/learning/revise-again/");
  await expect(page.getByRole("heading", { level: 1, name: "Revise again today" })).toBeVisible();
  const minutes = page.getByLabel("Minutes a day");
  await minutes.fill("301");
  await page.getByRole("button", { name: "Save and re-plan" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Minutes a day: Ensure this value is less than or equal to 300.",
  );
  await expect(minutes).toHaveAttribute("aria-invalid", "true");
  await minutes.fill("45");
  await page.getByRole("button", { name: "Save and re-plan" }).click();
  await expect(page.getByText(/At 45 minutes a day/)).toBeVisible();
});
