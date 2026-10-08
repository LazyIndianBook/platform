// The states spec's servers and fixtures: a second Django started with some settings (SHOP_OPEN=0, cash on delivery,
// Turnstile's test keys …) and a second Next server in front of it, on the suite's own database and build; a student
// under 18 whose parent has not confirmed; two rows of the PIN directory. Each is undone by the spec.
import { type ChildProcess, execFileSync, spawn } from "node:child_process";
import path from "node:path";

import { djangoEnv } from "../playwright.config";

const DJANGO_DIR = path.resolve(__dirname, "../../examleaf-web");
const python = process.env.DJANGO_PYTHON ?? path.join(DJANGO_DIR, ".venv/bin/python");

async function answers(url: string, timeout = 90_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (
      await fetch(url).then(
        (response) => response.ok,
        () => false,
      )
    )
      return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`${url} did not answer`);
}

/** Django on apiPort with `settings`, and the production build on webPort in front of it. */
export async function startSite(apiPort: number, webPort: number, settings: Record<string, string>) {
  const site = `http://localhost:${webPort}`;
  const processes: ChildProcess[] = [
    spawn(python, ["manage.py", "runserver", String(apiPort), "--noreload"], {
      cwd: DJANGO_DIR,
      env: { ...process.env, ...djangoEnv, SITE_URL: site, CSRF_TRUSTED_ORIGINS: site, ...settings },
      stdio: "ignore",
    }),
    spawn(process.execPath, [require.resolve("next/dist/bin/next"), "start", "-p", String(webPort)], {
      cwd: path.resolve(__dirname, ".."),
      env: { ...process.env, API_INTERNAL_BASE: `http://localhost:${apiPort}` },
      stdio: "ignore",
    }),
  ];
  await answers(`http://localhost:${apiPort}/api/v1/config/`);
  await answers(`${site}/api/health/`);
  return { site, stop: () => processes.forEach((child) => child.kill()) };
}

function shell(code: string): string {
  return execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: DJANGO_DIR,
    env: { ...process.env, ...djangoEnv },
    stdio: "pipe",
  }).toString();
}

const py = (value: string) => JSON.stringify(value);

/** A 15-year-old with a confirmed email address whose parent was asked but has not confirmed. */
export function createMinor(email: string, password: string) {
  shell(`
from datetime import date
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import User
user = User.objects.create_user(${py(email)}, ${py(password)}, full_name="E2E Minor", class_level=12, date_of_birth=date(date.today().year - 15, 1, 1), parent_name="E2E Parent", parent_contact="parent@example.com", consent_at=timezone.now())
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
`);
}

export function deleteUser(email: string) {
  shell(`from accounts.models import User; User.objects.filter(email=${py(email)}).delete()`);
}

/** PIN codes no post office has (9xxxxx is the Army Postal Service's): one in Assam, one on the Assam–Meghalaya line. */
export const PINS = { assam: "999991", border: "999992" };

export function addPins() {
  shell(`
from shop.models import PinCode
PinCode.objects.update_or_create(pin=${py(PINS.assam)}, defaults={"states": ["AS"], "districts": ["E2E District"]})
PinCode.objects.update_or_create(pin=${py(PINS.border)}, defaults={"states": ["AS", "ML"], "districts": ["E2E District", "E2E Hills"]})
`);
}

export function removePins() {
  shell(
    `from shop.models import PinCode; PinCode.objects.filter(pin__in=${py(Object.values(PINS).join(","))}.split(",")).delete()`,
  );
}
