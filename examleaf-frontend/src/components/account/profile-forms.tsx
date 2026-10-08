"use client";

// The account's short forms: Details (PATCH me/: name, board, class, district; the email address shown, changed on
// Log-in and security after a code) and Teacher access (POST me/teacher/, once: request, then checking, then
// verified; there is no view of students, G14). Each saves through the typed client, shows the API's errors beside
// their boxes, then reads the page again.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDate } from "@/lib/dates";

import { useAction } from "./use-action";

type DetailsProps = {
  fullName: string;
  classLevel: number | null;
  board: number | null;
  district: string;
  boards: { id: number; label: string }[];
  /** The account's email address, shown between the name and the board (it changes on Log-in and security). */
  email?: string;
  verified?: boolean | null;
};

export function DetailsForm({ fullName, classLevel, board, district, boards, email, verified }: DetailsProps) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <ErrorSummary
        error={error}
        labels={{ full_name: "Full name", class_level: "Class", board: "Board", district: "District" }}
      />
      <form
        className="flex max-w-[28rem] flex-col gap-[18px]"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const text = (name: string) => String(form.get(name) ?? "").trim();
          const level = Number(text("class_level"));
          const ok = await run(() =>
            personal(
              api.PATCH("/api/v1/me/", {
                body: {
                  full_name: text("full_name"),
                  class_level: level === 10 || level === 12 ? level : null,
                  board: Number(text("board")) || null,
                  district: text("district"),
                },
              }),
            ),
          );
          if (ok) {
            toast.success("Your details are saved.");
            router.refresh();
          }
        }}
      >
        <Field id="full_name" label="Full name" required error={fieldError(error, "full_name")}>
          <Input name="full_name" autoComplete="name" maxLength={120} defaultValue={fullName} />
        </Field>
        {email ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-base leading-snug font-semibold">Email address</span>
            <span className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-3 [overflow-wrap:anywhere]">
              {email}
              {verified ? <Badge variant="paid">Verified</Badge> : null}
            </span>
            <Link
              href="/account/security/#change-email"
              className="inline-flex min-h-11 items-center text-sm font-semibold"
            >
              Change, in Log-in and security
            </Link>
          </div>
        ) : null}
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(140px,100%),1fr))] gap-3.5">
          <Field id="board" label="Board" error={fieldError(error, "board")}>
            <Select name="board" defaultValue={board ?? ""}>
              <option value="">Not given</option>
              {boards.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="class_level" label="Class" error={fieldError(error, "class_level")}>
            <Select name="class_level" defaultValue={classLevel ?? ""}>
              <option value="">Not given</option>
              <option value="12">Class 12</option>
              <option value="10">Class 10</option>
            </Select>
          </Field>
        </div>
        <Field id="district" label="District" optional error={fieldError(error, "district")}>
          <Input name="district" autoComplete="address-level2" maxLength={80} defaultValue={district} />
        </Field>
        <div>
          <Button type="submit" busy={busy} className="max-nav:w-full">
            Save changes
          </Button>
        </div>
      </form>
    </>
  );
}

export function TeacherForm({ subjects = [] }: { subjects?: string[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <ErrorSummary
        error={error}
        labels={{ school_name: "School name", district: "District", subject: "Subject you teach" }}
      />
      <form
        className="flex flex-col gap-3.5"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const text = (name: string) => String(form.get(name) ?? "").trim();
          const ok = await run(() =>
            personal(
              api.POST("/api/v1/me/teacher/", {
                body: { school_name: text("school_name"), district: text("district"), subject: text("subject") },
              }),
            ),
          );
          if (ok) router.refresh();
        }}
      >
        <Field id="school_name" label="School name" required error={fieldError(error, "school_name")}>
          <Input name="school_name" autoComplete="organization" maxLength={200} />
        </Field>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(180px,100%),1fr))] gap-3">
          <Field id="district" label="District" required error={fieldError(error, "district")}>
            <Input name="district" autoComplete="address-level2" maxLength={80} />
          </Field>
          <Field id="subject" label="Subject you teach" required error={fieldError(error, "subject")}>
            {subjects.length ? (
              <Select name="subject" defaultValue={subjects[0]}>
                {subjects.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            ) : (
              <Input name="subject" maxLength={80} />
            )}
          </Field>
        </div>
        <div>
          <Button type="submit" busy={busy} className="max-nav:w-full">
            Ask for teacher access
          </Button>
        </div>
      </form>
    </>
  );
}

type Teacher = components["schemas"]["Teacher"];

/** Teacher access in its three states, from GET me/teacher/: not asked (the form), being checked, verified. Nothing
 *  more: a teacher's view of students needs a link the API does not have yet (G14). */
export function TeacherAccess({ request, subjects }: { request: Teacher | null; subjects?: string[] }) {
  if (!request) return <TeacherForm subjects={subjects} />;
  if (request.verified) {
    return (
      <Alert variant="success" title="You are a verified teacher.">
        <p>
          At {request.school_name}, {request.district}
          {request.verified_at ? `, since ${formatDate(request.verified_at)}` : ""}.
        </p>
      </Alert>
    );
  }
  return (
    <Alert variant="info" title="We are checking your request.">
      <p>
        {request.school_name}, {request.district} ({request.subject}), asked on {formatDate(request.created)}. Once we
        have checked with your school, this page shows you as a verified teacher.
      </p>
    </Alert>
  );
}
