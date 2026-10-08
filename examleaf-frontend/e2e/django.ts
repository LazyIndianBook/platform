// What the smoke tests need from the Django backend beyond HTTP: the codes it "emailed" (the console backend prints
// them to its log) and the clean-up of the accounts the tests made.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { djangoEnv } from "../playwright.config";

const DJANGO_DIR = path.resolve(__dirname, "../../examleaf-web");

/** The 6-digit code in the latest email to `to`, waiting for it to be printed. */
export async function emailedCode(to: string, after = 0, timeout = 15_000): Promise<string> {
  const log = process.env.DJANGO_LOG!;
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const text = readFileSync(log, "utf8");
    const start = text.lastIndexOf(`To: ${to}`);
    if (start >= after && start !== -1) {
      const code = /^(\d{6})\r?$/m.exec(text.slice(start))?.[1]; // the text part: the code on a line of its own
      if (code) return code;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`no code emailed to ${to} in ${log}`);
}

/** Where the log ends now: a later code is one sent after this point. */
export function logLength(): number {
  return readFileSync(process.env.DJANGO_LOG!, "utf8").length;
}

/** Deletes the accounts the tests made (their emails start with "e2e-"). */
export function deleteTestUsers() {
  const python = process.env.DJANGO_PYTHON ?? path.join(DJANGO_DIR, ".venv/bin/python");
  execFileSync(
    python,
    [
      "manage.py",
      "shell",
      "-c",
      "from accounts.models import User; print(User.objects.filter(email__startswith='e2e-').delete())",
    ],
    { cwd: DJANGO_DIR, env: { ...process.env, ...djangoEnv }, stdio: "pipe" },
  );
}
