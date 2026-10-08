// The account tests' fixtures in the Django backend (manage.py shell): a student with a confirmed email address and
// a password, a book code from manage.py make_book_codes, and the clean-up of both (the student's attempts, consents
// and entitlements go with the account).
import { execFileSync } from "node:child_process";
import path from "node:path";

import { djangoEnv } from "../playwright.config";

const DJANGO_DIR = path.resolve(__dirname, "../../examleaf-web");
const python = process.env.DJANGO_PYTHON ?? path.join(DJANGO_DIR, ".venv/bin/python");
// the codes' key: the server's LEARN_CODE_SECRET, or the key a server without one uses (learn.models.code_digest)
const codeSecret = process.env.LEARN_CODE_SECRET || "examleaf-book-codes";

function manage(...args: string[]): string {
  return execFileSync(python, ["manage.py", ...args], {
    cwd: DJANGO_DIR,
    env: { ...process.env, ...djangoEnv, LEARN_CODE_SECRET: codeSecret },
    stdio: "pipe",
  }).toString();
}

const py = (value: string) => JSON.stringify(value);

export function createStudent(email: string, password: string) {
  manage(
    "shell",
    "-c",
    `
from datetime import date
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import User
user = User.objects.create_user(${py(email)}, ${py(password)}, full_name="C E2E Student", class_level=12, date_of_birth=date(2000, 1, 1), consent_at=timezone.now())
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
`,
  );
}

/** One new book code for a subject (PHY …), as printed: XXXX-XXXX-XXXX. */
export function makeBookCode(subject: string, batch: string): string {
  const csv = manage("make_book_codes", subject, "1", "--batch", batch);
  return csv.trim().split("\n")[1].split(",")[0];
}

export function deleteStudent(email: string, batch: string) {
  manage(
    "shell",
    "-c",
    `
from accounts.models import User
from learn.models import BookCode
print(User.objects.filter(email=${py(email)}).delete(), BookCode.objects.filter(batch=${py(batch)}).delete())
`,
  );
}
