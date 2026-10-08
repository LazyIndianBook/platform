"use client";

// A locked chapter's book-code card (Chapter locked): POST learn/redeem/, 5 tries an hour per student and per address.
// The API decides: a refusal comes back in its words (the summary and beside the box); an accepted code is said in a
// toast and the page is read again, so whatever the code opened shows as open. The code typed survives a log-in round
// trip in this tab; while a parent's consent is awaited the form is off and says why.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { ConsentPending } from "@/components/account/parts";
import { useAction } from "@/components/account/use-action";
import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { codeProblem } from "@/components/revision/islands";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDate } from "@/lib/dates";

import { readDraft, writeDraft } from "./draft";

const DRAFT = "examleaf:course:book-code";

export function RedeemCard({ subject, consentPending }: { subject: string; consentPending: boolean }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const box = useRef<HTMLInputElement>(null);
  const shown = codeProblem(error);

  useEffect(() => {
    const draft = readDraft<string>(DRAFT);
    if (draft && box.current) box.current.value = draft;
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = String(new FormData(event.currentTarget).get("code") ?? "").trim();
    writeDraft(DRAFT, code);
    let opened: components["schemas"]["Entitlement"] | undefined;
    const ok = await run(async () => {
      opened = await personal(api.POST("/api/v1/learn/redeem/", { body: { code } }));
    });
    if (!ok || !opened) return;
    writeDraft(DRAFT, null);
    const what = opened.subject_name ?? "Every subject";
    toast.success(
      `${opened.valid_until ? `${what} is open until ${formatDate(opened.valid_until)}.` : `${what} is open.`} Every clip, card and quiz question.`,
    );
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-3 self-start border-[1.5px] border-foreground bg-card p-6 [&_p]:m-0">
      <h2 className="font-head text-2xl leading-[1.15] font-semibold tracking-normal">Open all of {subject}</h2>
      <p className="text-[15px] leading-[1.55] text-ink/85">
        Type the 12-character code printed in your ExamLeaf {subject} book. It opens the subject for a year.
      </p>
      {consentPending ? <ConsentPending what="you can watch the free clips but not use a book code" /> : null}
      <ErrorSummary error={shown} labels={{ code: "Book code" }} />
      <form noValidate onSubmit={submit}>
        <fieldset disabled={consentPending} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
          <Field
            id="code"
            label="Book code"
            help="Spaces and dashes don't matter. No 0, O, 1 or I."
            error={fieldError(shown, "code")}
          >
            <Input
              ref={box}
              name="code"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={40}
              className="min-h-[52px] font-mono text-lg tracking-[0.12em]"
            />
          </Field>
          <Button type="submit" size="lg" block busy={busy}>
            Open the subject
          </Button>
        </fieldset>
      </form>
      <p className="text-sm text-muted-foreground">
        No code?{" "}
        <Link href="/shop/" className="font-bold">
          Get the course in the shop
        </Link>
      </p>
    </div>
  );
}
