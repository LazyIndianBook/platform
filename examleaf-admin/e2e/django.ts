// What the console's tests need from the Django backend beyond HTTP: staff members to sign in with (an ADMIN with a
// confirmed email address, a password and an authenticator app with a known secret), made and deleted through
// manage.py shell, and the authenticator's codes (RFC 6238, as allauth checks them).
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import path from "node:path";

import { djangoDir, djangoEnv } from "../playwright.config";

const python = process.env.DJANGO_PYTHON ?? path.join(djangoDir, ".venv/bin/python");

function shell(code: string): string {
  return execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: djangoDir,
    env: { ...process.env, ...djangoEnv },
    stdio: "pipe",
  }).toString();
}

const py = (value: string) => JSON.stringify(value);

export type Staff = { email: string; password: string; secret: string; name: string };

/** A base32 secret of 32 letters, as an authenticator app keeps it. */
export function newSecret(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  return Array.from({ length: 32 }, () => alphabet[Math.floor(Math.random() * 32)]).join("");
}

/** A member of staff with the role group (ADMIN by default) and an authenticator app. */
export function createStaff(staff: Staff, role = "ADMIN") {
  shell(`
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import TOTP
from django.contrib.auth.models import Group
from accounts.models import User
User.objects.filter(email=${py(staff.email)}).delete()
user = User.objects.create_user(${py(staff.email)}, ${py(staff.password)}, full_name=${py(staff.name)}, is_staff=True)
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
user.groups.add(Group.objects.get(name=${py(role)}))
TOTP.activate(user, ${py(staff.secret)})
`);
}

/** Deletes the members of staff the tests made (their emails start with "admin-ui-"). */
export function deleteStaff(emails: string[]) {
  shell(`
from accounts.models import User
print(User.objects.filter(email__in=${JSON.stringify(emails)}, email__startswith="admin-ui-").delete())
`);
}

/** The authenticator app's code for a moment (RFC 6238: HMAC-SHA1, 30 s, 6 digits). */
export function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.toUpperCase()) bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0xf;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** A code allauth has not seen used yet: each code works once (allauth marks it used for its 30 s), so wait for the
 *  next one when `used` is this one. */
export async function freshCode(secret: string, used: string | null): Promise<string> {
  let code = totp(secret);
  while (code === used) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    code = totp(secret);
  }
  return code;
}
