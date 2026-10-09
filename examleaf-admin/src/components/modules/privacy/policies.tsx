"use client";

// A legal page's versions: publishing a new one (POST privacy/policies/{slug}/publish/: the text in Markdown, its title,
// a line on what it changes, in force today or from a later day, never backdated) and cancelling one that waits for
// its day (POST cancel-scheduled/, with a reason). The API numbers the versions and refuses the text in force.
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { cancelScheduledPolicy, type PolicyDetail, type PolicySlug, publishPolicy } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

export function PublishPolicy({ policy, today }: { policy: PolicyDetail; today: string }) {
  const can = useCan();
  if (!can(P.policiesPublish)) return null;
  const id = `publish-${policy.slug}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.legal.publishButton}
      success={copy.legal.published}
      className="flex max-w-[52rem] flex-col gap-4"
      labels={{
        title: copy.legal.publishTitle,
        summary: copy.legal.publishSummary,
        effective_from: copy.legal.publishFrom,
        markdown: copy.legal.publishText,
      }}
      onSubmit={(form) =>
        publishPolicy(policy.slug as PolicySlug, {
          markdown: String(form.get("markdown") ?? ""),
          title: formText(form, "title"),
          summary: formText(form, "summary"),
          ...(formText(form, "effective_from") ? { effective_from: formText(form, "effective_from") } : {}),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id={`${id}-title`} label={copy.legal.publishTitle} error={fieldError(error, "title")}>
              <Input name="title" defaultValue={policy.title} maxLength={120} autoComplete="off" />
            </Field>
            <Field
              id={`${id}-effective_from`}
              label={copy.legal.publishFrom}
              help={copy.legal.publishFromHelp}
              error={fieldError(error, "effective_from")}
            >
              <Input name="effective_from" type="date" min={today} defaultValue={today} />
            </Field>
          </FormGrid>
          <Field
            id={`${id}-summary`}
            label={copy.legal.publishSummary}
            help={copy.legal.publishSummaryHelp}
            error={fieldError(error, "summary")}
          >
            <Input name="summary" maxLength={200} autoComplete="off" aria-required="true" />
          </Field>
          <Field id={`${id}-markdown`} label={copy.legal.publishText} error={fieldError(error, "markdown")}>
            <Textarea
              name="markdown"
              rows={18}
              defaultValue={policy.markdown}
              aria-required="true"
              className="font-mono text-sm"
            />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function CancelScheduled({ slug }: { slug: string }) {
  const can = useCan();
  if (!can(P.policiesPublish)) return null;
  return (
    <ConfirmDialog
      triggerLabel={copy.legal.cancelScheduled}
      title={copy.legal.cancelScheduledTitle}
      text={copy.legal.cancelScheduledText}
      confirmLabel={copy.legal.cancelScheduled}
      reason
      success={copy.legal.scheduleCancelled}
      onConfirm={({ reason }) => cancelScheduledPolicy(slug as PolicySlug, reason)}
    />
  );
}
