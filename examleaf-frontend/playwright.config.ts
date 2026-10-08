// Playwright smoke tests (e2e/), Chromium only, against a production build of the frontend and a Django backend.
// Locally both servers already running are reused (npm run dev, and Django on :8100 with DJANGO_LOG pointing at its
// log); in CI scripts/e2e-backend.sh seeds and starts Django, and `npm run start` serves the build. E2E_WEB_PORT and
// E2E_API_PORT move them (two builders side by side on one machine: 3001 and 8101).
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const DJANGO_DIR = path.resolve(__dirname, "../examleaf-web");
process.env.DJANGO_LOG ??= path.resolve(__dirname, ".e2e/django.log");
const WEB_PORT = process.env.E2E_WEB_PORT ?? "3000";
const API_PORT = process.env.E2E_API_PORT ?? "8100";
const SITE = `http://localhost:${WEB_PORT}`;

// the backend's environment, for the server and for the tests' clean-up through manage.py shell
export const djangoEnv = {
  DEBUG: "1",
  SECRET_KEY: process.env.SECRET_KEY ?? "dev-e2e-only-not-secret",
  ALLOWED_HOSTS: "localhost,127.0.0.1",
  SITE_URL: SITE,
  CSRF_TRUSTED_ORIGINS: SITE,
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
    baseURL: SITE,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: /phone\.spec\.ts/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /phone\.spec\.ts/ },
  ],
  webServer: [
    {
      command: "sh scripts/e2e-backend.sh",
      url: `http://localhost:${API_PORT}/api/v1/config/`,
      env: {
        ...djangoEnv,
        DJANGO_LOG: process.env.DJANGO_LOG,
        DJANGO_PYTHON: process.env.DJANGO_PYTHON ?? "python",
        DJANGO_PORT: API_PORT,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
    {
      command: `npm run start -- -p ${WEB_PORT}`,
      url: `${SITE}/api/health/`,
      env: { API_INTERNAL_BASE: `http://localhost:${API_PORT}`, NEXT_PUBLIC_SITE_URL: SITE },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  metadata: { djangoDir: DJANGO_DIR },
});
