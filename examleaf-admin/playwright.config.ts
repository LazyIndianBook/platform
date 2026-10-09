// Playwright tests of the console (e2e/), Chromium, against `next dev` and a real Django, in one of two ways:
//   mock (the default; project "chromium", e2e/console.spec.ts): STAFF_API_MOCK=1, the staff API answered from the
//        fixtures of src/mocks/staff/, Django only for signing in. Quick, and every state the console draws.
//   real (E2E_STAFF_API=real; project "real", e2e/real.spec.ts): the console against the staff API as built, with an
//        OWNER and a SUPPORT member made for the run and the records the journey works on (e2e/django.ts).
// Both servers already running are reused (development: the console on 3020, Django on 8103); otherwise
// scripts/e2e-backend.sh migrates and starts Django on a SQLite file of its own (.e2e/db.sqlite3) and `next dev`
// starts the console. E2E_WEB_PORT and E2E_API_PORT move them; DJANGO_DATABASE_URL points Django elsewhere (a copy of
// the seeded e2e database, for instance).
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const REAL = process.env.E2E_STAFF_API === "real";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "3020";
const API_PORT = process.env.E2E_API_PORT ?? "8103";
const SITE = `http://localhost:${WEB_PORT}`;
const DJANGO_DIR = path.resolve(__dirname, "../examleaf-web");
process.env.DJANGO_LOG ??= path.resolve(__dirname, ".e2e/django.log");

// a SQLite database takes the console's parallel calls with immediate transactions and a 20 s wait: without them
// allauth.usersessions' write on every request answers "database is locked"
const DATABASE_URL = (
  process.env.DJANGO_DATABASE_URL ?? `sqlite:///${path.resolve(__dirname, ".e2e/db.sqlite3")}`
).replace(/^(sqlite:[^?]*)$/, "$1?transaction_mode=IMMEDIATE&timeout=20");

const INTERNAL_TOKEN = process.env.INTERNAL_API_TOKEN ?? "e2e-internal-token";

/** The backend's environment, for the server and for the tests' set-up through manage.py shell. */
export const djangoEnv = {
  DEBUG: "1",
  SECRET_KEY: process.env.SECRET_KEY ?? "dev-e2e-only-not-secret",
  ALLOWED_HOSTS: "localhost,127.0.0.1",
  SITE_URL: SITE,
  CSRF_TRUSTED_ORIGINS: SITE,
  USE_X_FORWARDED_HOST: "1",
  INTERNAL_API_TOKEN: INTERNAL_TOKEN,
  DATABASE_URL,
};

export const djangoDir = DJANGO_DIR;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 300_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  // an action that cannot happen fails within 30 s (a first visit compiles under next dev), not at the test's 5 minutes
  use: { baseURL: SITE, trace: "retain-on-failure", actionTimeout: 30_000 },
  projects: [
    REAL
      ? { name: "real", testMatch: /real\.spec\.ts/, use: { ...devices["Desktop Chrome"] } }
      : { name: "chromium", testMatch: /console\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "sh scripts/e2e-backend.sh",
      url: `http://localhost:${API_PORT}/api/v1/config/`,
      env: {
        ...djangoEnv,
        DJANGO_LOG: process.env.DJANGO_LOG,
        DJANGO_PYTHON: process.env.DJANGO_PYTHON ?? path.join(DJANGO_DIR, ".venv/bin/python"),
        DJANGO_PORT: API_PORT,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
    {
      command: `npx next dev --port ${WEB_PORT}`,
      url: `${SITE}/api/health/`,
      env: {
        STAFF_API_MOCK: REAL ? "" : "1",
        API_INTERNAL_BASE: `http://localhost:${API_PORT}`,
        NEXT_PUBLIC_SITE_URL: SITE,
        NEXT_PUBLIC_WEBSITE_URL: process.env.E2E_WEBSITE_URL ?? "http://localhost:3000",
        NEXT_PUBLIC_ERP_URL: "https://erp.example.invalid",
        INTERNAL_API_TOKEN: INTERNAL_TOKEN,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
