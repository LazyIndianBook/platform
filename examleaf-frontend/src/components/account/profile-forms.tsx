"use client";

// The account's short forms: Details (PATCH me/: name, class, board, district) and Teacher access (POST me/teacher/,
// once). Each saves through the typed client, shows the API's errors beside their boxes, then reads the page again.
import { useRouter } from "next/navigation";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";

import { useAction } from "./use-action";

type DetailsProps = {
  fullName: string;
  classLevel: number | null;
  board: number | null;
  district: string;
  boards: { id: number; label: string }[];
};

export function DetailsForm({ fullName, classLevel, board, district, boards }: DetailsProps) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <ErrorSummary
        error={error}
        labels={{ full_name: "Full name", class_level: "Class", board: "Board", district: "District" }}
      />
      <form
        className="flex flex-col gap-4"
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
        <FormGrid>
          <Field id="class_level" label="Class" error={fieldError(error, "class_level")}>
            <Select name="class_level" defaultValue={classLevel ?? ""}>
              <option value="">Not given</option>
              <option value="12">Class 12</option>
              <option value="10">Class 10</option>
            </Select>
          </Field>
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
        </FormGrid>
        <Field id="district" label="District" optional error={fieldError(error, "district")}>
          <Input name="district" autoComplete="address-level2" maxLength={80} defaultValue={district} />
        </Field>
        <div>
          <Button type="submit" busy={busy}>
            Save my details
          </Button>
        </div>
      </form>
    </>
  );
}

export function TeacherForm() {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <ErrorSummary
        error={error}
        labels={{ school_name: "School or college", district: "District", subject: "Subject you teach" }}
      />
      <form
        className="flex flex-col gap-4"
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
          if (ok) {
            toast.success(
              "Thank you. Once we have checked with your school, this page shows you as a verified teacher.",
            );
            router.refresh();
          }
        }}
      >
        <Field id="school_name" label="School or college" required error={fieldError(error, "school_name")}>
          <Input name="school_name" autoComplete="organization" maxLength={200} />
        </Field>
        <FormGrid>
          <Field id="district" label="District" required error={fieldError(error, "district")}>
            <Input name="district" autoComplete="address-level2" maxLength={80} />
          </Field>
          <Field id="subject" label="Subject you teach" required error={fieldError(error, "subject")}>
            <Input name="subject" maxLength={80} />
          </Field>
        </FormGrid>
        <div>
          <Button type="submit" busy={busy}>
            Send
          </Button>
        </div>
      </form>
    </>
  );
}
