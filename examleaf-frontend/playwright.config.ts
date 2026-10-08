// Playwright smoke tests (e2e/), Chromium only, against a production build of the frontend and a Django backend.
// Locally both servers already running are reused (npm run dev, and Django on :8100 with DJANGO_LOG pointing at its
// log); in CI scripts/e2e-backend.sh seeds and starts Django, and `npm run start` serves the build.
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const DJANGO_DIR = path.resolve(__dirname, "../examleaf-web");
process.env.DJANGO_LOG ??= path.resolve(__dirname, ".e2e/django.log");

// the backend's environment, for the server and for the tests' clean-up through manage.py shell
export const djangoEnv = {
  DEBUG: "1",
  SECRET_KEY: process.env.SECRET_KEY ?? "dev-e2e-only-not-secret",
  ALLOWED_HOSTS: "localhost,127.0.0.1",
  SITE_URL: "http://localhost:3000",
  CSRF_TRUSTED_ORIGINS: "http://localhost:3000",
  USE_X_FORWARDED_HOST: "1",
  ...(process.env.DJANGO_DATABASE_URL ? { DATABASE_URL: process.env.DJANGO_DATABASE_URL } : {}),
};

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: /phone\.spec\.ts/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /phone\.spec\.ts/ },
  ],
  webServer: [
    {
      command: "sh scripts/e2e-backend.sh",
      url: "http://localhost:8100/api/v1/config/",
      env: { ...djangoEnv, DJANGO_LOG: process.env.DJANGO_LOG, DJANGO_PYTHON: process.env.DJANGO_PYTHON ?? "python" },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
    {
      command: "npm run start -- -p 3000",
      url: "http://localhost:3000/api/health/",
      env: { API_INTERNAL_BASE: "http://localhost:8100", NEXT_PUBLIC_SITE_URL: "http://localhost:3000" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  metadata: { djangoDir: DJANGO_DIR },
});
