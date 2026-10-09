// The account tests' fixtures in the Django backend (manage.py shell): a student with a confirmed email address and
// a password, a book code from manage.py make_book_codes, a teacher request verified as staff would, and the clean-up
// of both (the student's attempts, consents, entitlements and teacher request go with the account).
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

/** For Learning (8E): a Physics chapter of its own (`title`, numbered after the others) with a published revision of
 *  three processed clips (no files: nothing plays) and a quiz item; the student, open to Physics for a year, has
 *  watched the first clip and answered the quiz item wrong yesterday (so it is due again today). */
export function seedLearning(email: string, title: string) {
  manage(
    "shell",
    "-c",
    `
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone
from accounts.models import User
from content.models import Subject
from learn.models import Chapter, Clip, Entitlement, Progress, QuizAttempt, QuizItem, Revision
user, subject, title = User.objects.get(email=${py(email)}), Subject.objects.get(code="PHY"), ${py(title)}
number = (Chapter.objects.filter(subject=subject).aggregate(n=Max("number"))["n"] or 0) + 1
chapter = Chapter.objects.create(subject=subject, number=number, title=title, weight=5, frequency=3)
revision = Revision.objects.create(chapter=chapter, title=f"Revise {title}", status="published")
clips = [Clip.objects.create(revision=revision, order=i, title=f"{title}: clip {i}", processing="ready", duration=120, hls_path=f"learn/hls/{title}-{i}/v1/master.m3u8") for i in (1, 2, 3)]
Entitlement.objects.create(user=user, subject=subject, valid_until=timezone.localdate() + timedelta(days=365))
Progress.objects.create(user=user, clip=clips[0], seconds_watched=120, completed=True)
item = QuizItem.objects.create(chapter=chapter, kind="true_false", text="Charge is quantised.", answer="true")
QuizAttempt.objects.create(user=user, item=item, correct=False, created=timezone.now() - timedelta(days=1))
`,
  );
}

/** The students and the chapter of seedLearning (its revision, clips, quiz item and the students' rows go with them). */
export function deleteLearning(emails: string[], title: string) {
  manage(
    "shell",
    "-c",
    `
from accounts.models import User
from learn.models import Chapter
print(User.objects.filter(email__in=${JSON.stringify(emails)}, is_staff=False).delete(), Chapter.objects.filter(title=${py(title)}).delete())
`,
  );
}

/** Staff's step of teacher access, as the admin does it: the request verified (the TEACHER role is the admin's). */
export function verifyTeacher(email: string) {
  manage(
    "shell",
    "-c",
    `
from django.utils import timezone
from accounts.models import TeacherProfile
print(TeacherProfile.objects.filter(user__email=${py(email)}).update(verified=True, verified_at=timezone.now()))
`,
  );
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

/** The staff console's step of an impersonation (staff.services.impersonation_token, as POST staff/users/{id}/
 *  impersonate/ does it): a 15-minute token for the student, issued by a member of staff made for it (`staff`, no
 *  role, no password: they never log in here). Printed last, as the console's link carries it. */
export function impersonationToken(email: string, staff: string): string {
  const out = manage(
    "shell",
    "-c",
    `
from accounts.models import User
from staff.services import impersonation_token
member = User.objects.filter(email=${py(staff)}).first() or User.objects.create_user(${py(staff)}, None, full_name="C E2E Support", is_staff=True)
token, _ = impersonation_token(member, User.objects.get(email=${py(email)}), reason="The website's e2e: a customer's question", ticket="C-E2E-1")
print(token)
`,
  );
  return out.trim().split("\n").at(-1) ?? "";
}

/** The member of staff of impersonationToken (the audit events keep their id only). */
export function deleteStaffMember(staff: string) {
  manage("shell", "-c", `from accounts.models import User\nprint(User.objects.filter(email=${py(staff)}).delete())`);
}
