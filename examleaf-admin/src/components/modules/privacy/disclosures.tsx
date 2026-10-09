"use client";

// The e-commerce disclosures and the privacy contacts (GET privacy/disclosures/), one form: each value in effect with
// where it comes from (the environment's, or set here) and whether the website shows it. What changed is counted in
// the save bar at the foot of the window, saved together with one reason (PUT privacy/disclosures/ with only the
// changed keys: each a setting.changed event), or undone; leaving the page with changes unsaved asks first. The API
// checks each value (its length, its choices, a date) and answers in its words beside the field.
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Facts } from "@/components/data/record-page";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { type DisclosureSetting, saveDisclosures } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));

/** What the field's help says: where the value comes from, the environment's value when set here, the website. */
function origin(setting: DisclosureSetting) {
  return [
    labelOf(copy.legal.source, setting.source),
    setting.source === "database" && text(setting.environment)
      ? copy.legal.environmentValue(text(setting.environment))
      : "",
    setting.public ? copy.legal.publicField : copy.legal.privateField,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** The settings whose value differs from the one in effect. */
export function changedValues(settings: DisclosureSetting[], values: Record<string, string>) {
  return Object.fromEntries(
    settings
      .filter((setting) => values[setting.key] !== text(setting.value))
      .map((setting) => [setting.key, values[setting.key]]),
  );
}

export function DisclosuresView({ settings }: { settings: DisclosureSetting[] }) {
  return (
    <Facts
      items={settings.map((setting) => ({
        label: setting.label,
        value: (
          <>
            <span className="whitespace-pre-wrap">
              {Array.isArray(setting.kind)
                ? labelOf(copy.legal.choices, text(setting.value))
                : text(setting.value) || copy.legal.emptyValue}
            </span>
            <span className="block text-sm text-muted-foreground">{origin(setting)}</span>
          </>
        ),
      }))}
    />
  );
}

export function DisclosuresForm({ settings }: { settings: DisclosureSetting[] }) {
  const id = useId();
  const router = useRouter();
  const initial = Object.fromEntries(settings.map((setting) => [setting.key, text(setting.value)]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [reason, setReason] = useState("");
  const { run, busy, error, setError } = useAction();
  const changed = changedValues(settings, values);
  const count = Object.keys(changed).length;

  // leaving with changes unsaved (a reload, closing the tab) asks first
  useEffect(() => {
    if (!count) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = copy.legal.leaveWarning;
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [count]);

  const labels = {
    ...Object.fromEntries(settings.map((setting) => [setting.key, setting.label])),
    reason: copy.common.reason,
  };
  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={async (event) => {
        event.preventDefault();
        const ok = await run(() => saveDisclosures(changed, reason.trim()));
        if (!ok) return;
        setReason("");
        toast.success(copy.legal.disclosuresSaved);
        router.refresh();
      }}
    >
      <ErrorSummary error={error} labels={labels} idPrefix={`${id}-`} />
      <div className="flex max-w-[44rem] flex-col gap-5">
        {settings.map((setting) => {
          const name = setting.key;
          const field = `${id}-${name}`;
          const set = (value: string) => setValues((current) => ({ ...current, [name]: value }));
          const control = Array.isArray(setting.kind) ? (
            <Select name={name} value={values[name]} onChange={(event) => set(event.target.value)}>
              {(setting.kind as string[]).map((choice) => (
                <option key={choice} value={choice}>
                  {labelOf(copy.legal.choices, choice)}
                </option>
              ))}
            </Select>
          ) : setting.max_length > 300 ? (
            <Textarea
              name={name}
              rows={5}
              maxLength={setting.max_length}
              value={values[name]}
              onChange={(event) => set(event.target.value)}
            />
          ) : (
            <Input
              name={name}
              maxLength={setting.max_length}
              autoComplete="off"
              value={values[name]}
              onChange={(event) => set(event.target.value)}
            />
          );
          return (
            <Field key={name} id={field} label={setting.label} help={origin(setting)} error={fieldError(error, name)}>
              {control}
            </Field>
          );
        })}
      </div>
      {count ? (
        <div
          role="region"
          aria-label={copy.legal.saveChanges}
          className="sticky bottom-0 z-10 flex flex-col gap-3 border-t-[1.5px] border-foreground bg-background py-4"
        >
          <p className="m-0 font-semibold" aria-live="polite">
            {copy.legal.unsaved(count)}
          </p>
          <Field
            id={`${id}-reason`}
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Input
              name="reason"
              autoComplete="off"
              aria-required="true"
              maxLength={300}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
          <div className="flex flex-wrap gap-3">
            <Button type="submit" busy={busy}>
              {copy.legal.saveChanges}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setValues(initial);
                setError(null);
              }}
            >
              {copy.legal.discard}
            </Button>
          </div>
        </div>
      ) : null}
    </form>
  );
}
