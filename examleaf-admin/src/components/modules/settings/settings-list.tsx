"use client";

// Site settings and feature flags, one shape (GET settings/ and flags/): each key with its value, where the value comes
// from (the server's environment, which only a deployment changes, or the console), from when it applies and who
// changed it last, its history, and, for a console value the person may change, the change itself (PUT
// settings/{key}/ or flags/{key}/: the new value, a reason, and optionally when it takes effect).
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Switch } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { changeSetting, type Setting, type SettingKind } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, fromLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

/** A value in words: On / Off, (empty), JSON for anything structured. */
export function valueText(value: unknown): string {
  if (value === true) return copy.settings.trueValue;
  if (value === false) return copy.settings.falseValue;
  if (value === null || value === undefined || value === "") return copy.settings.emptyValue;
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The new value from the form, of the current value's type. */
function readValue(form: FormData, current: unknown): unknown {
  if (typeof current === "boolean") return form.get("value") === "on";
  const text = formText(form, "value");
  if (typeof current === "number") return text === "" ? null : Number(text);
  if (current !== null && typeof current === "object") {
    try {
      return JSON.parse(text);
    } catch {
      throw new ApiError(400, "invalid", copy.errors.badRequest, { value: [copy.errors.badRequest] });
    }
  }
  return text;
}

function ValueField({ id, setting, error }: { id: string; setting: Setting; error: ApiError | null }) {
  const current = setting.value;
  if (typeof current === "boolean") {
    return (
      <div className="flex flex-col gap-1">
        <Switch name="value" defaultChecked={current}>
          {setting.key}
        </Switch>
      </div>
    );
  }
  return (
    <Field id={`${id}-value`} label={copy.settings.value} error={fieldError(error, "value")}>
      {current !== null && typeof current === "object" ? (
        <Textarea name="value" rows={4} defaultValue={JSON.stringify(current, null, 2)} className="font-mono" />
      ) : (
        <Input
          name="value"
          type={typeof current === "number" ? "number" : "text"}
          defaultValue={current === null || current === undefined ? "" : String(current)}
          autoComplete="off"
          aria-required="true"
        />
      )}
    </Field>
  );
}

function SettingRow({ kind, setting }: { kind: SettingKind; setting: Setting }) {
  const can = useCan();
  const changing = setting.source === "db" && can(kind === "settings" ? P.settingsChange : P.flagsChange);
  const id = `${kind}-${setting.key.replace(/[^a-z0-9_-]/gi, "_")}`;
  return (
    <li className="flex flex-col gap-3 border-b border-border py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1">
          <code className="text-[15px] font-semibold break-all">{setting.key}</code>
          <span className="text-[15px] break-words">{valueText(setting.value)}</span>
        </div>
        <StatusChip tone={setting.source === "env" ? "stopped" : "moving"}>
          {labelOf(copy.settings.sources, setting.source)}
        </StatusChip>
      </div>
      <p className="m-0 text-sm text-muted-foreground">
        {setting.source === "env"
          ? copy.settings.envNote
          : [
              setting.effective_from
                ? `${copy.settings.columns.effective}: ${formatDateTime(setting.effective_from)}`
                : "",
              setting.changed_by
                ? `${copy.settings.columns.changedBy}: ${setting.changed_by.name || setting.changed_by.email}`
                : "",
              setting.reason ? `“${setting.reason}”` : "",
            ]
              .filter(Boolean)
              .join(" · ")}
      </p>
      <div className="flex flex-wrap gap-x-6">
        {changing ? (
          <details className="group basis-full">
            <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
              {copy.settings.change} <span className="sr-only">{setting.key}</span>
            </summary>
            <div className="pt-2">
              <ActionForm
                id={id}
                submitLabel={copy.settings.saveChange}
                success={copy.settings.changed}
                labels={{
                  value: copy.settings.value,
                  reason: copy.common.reason,
                  effective_from: copy.settings.effectiveFrom,
                }}
                onSubmit={(form) => {
                  const effective = formText(form, "effective_from");
                  return changeSetting(kind, setting.key, {
                    value: readValue(form, setting.value),
                    reason: formText(form, "reason"),
                    ...(effective ? { effective_from: fromLocalInput(effective) } : {}),
                  });
                }}
              >
                {(error) => (
                  <>
                    <ValueField id={id} setting={setting} error={error} />
                    <Field
                      id={`${id}-reason`}
                      label={copy.common.reason}
                      help={copy.common.reasonHelp}
                      error={fieldError(error, "reason")}
                    >
                      <Textarea name="reason" rows={2} aria-required="true" />
                    </Field>
                    <Field
                      id={`${id}-effective_from`}
                      label={copy.settings.effectiveFrom}
                      optional
                      help={copy.settings.effectiveHelp}
                      error={fieldError(error, "effective_from")}
                    >
                      <Input name="effective_from" type="datetime-local" className="w-auto" />
                    </Field>
                  </>
                )}
              </ActionForm>
            </div>
          </details>
        ) : null}
        <details className="basis-full">
          <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
            {copy.settings.history} <span className="sr-only">{setting.key}</span>
          </summary>
          {setting.history.length ? (
            <ol className="m-0 flex list-none flex-col gap-2 p-0 pt-2 text-[15px]">
              {setting.history.map((change, index) => (
                <li key={`${change.at}-${index}`} className="border-l-2 border-border pl-3">
                  <code className="break-all">{valueText(change.value)}</code>
                  <span className="block text-sm text-muted-foreground">
                    {copy.settings.historyEntry(
                      change.changed_by?.name || change.changed_by?.email || copy.common.unknown,
                      formatDateTime(change.at),
                    )}
                    {change.reason ? ` · “${change.reason}”` : ""}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="m-0 pt-2 text-[15px] text-muted-foreground">{copy.settings.noHistory}</p>
          )}
        </details>
      </div>
    </li>
  );
}

export function SettingsList({ kind, settings }: { kind: SettingKind; settings: Setting[] }) {
  return (
    <ul className="m-0 flex list-none flex-col border-t-[1.5px] border-foreground p-0">
      {settings.map((setting) => (
        <SettingRow key={setting.key} kind={kind} setting={setting} />
      ))}
    </ul>
  );
}
