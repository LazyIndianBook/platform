"use client";

// The site's switches and the feature flags (GET settings/ and flags/): each key with its value, where the value comes
// from (the environment, or the console), from when, who changed it last and why, the changes to come, its history
// (GET settings/{key}/ or flags/{key}/, read when opened), and, for whoever holds the permission the API names for it
// (a setting's `permission`; staff.manage_flags for a flag), the change itself (PUT settings/{key}/ or flags/{key}/:
// the new value, a reason, and optionally when it takes effect; null: back to the environment's).
import { useState } from "react";

import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Checkbox, Switch } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/errors";
import { changeFlag, changeSetting, type Flag, type Setting, switchHistory, type SwitchRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime, fromLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

type Kind = "settings" | "flags";
/** A setting's kind as the API names it: "bool", "str", or its allowed values; a flag's: any JSON. */
type ValueKind = "bool" | "str" | "json" | string[];

/** A value in words: On / Off, (empty), JSON for anything structured. */
export function valueText(value: unknown): string {
  if (value === true) return copy.settings.trueValue;
  if (value === false) return copy.settings.falseValue;
  if (value === null || value === undefined || value === "") return copy.settings.emptyValue;
  return typeof value === "string" ? value : JSON.stringify(value);
}

function kindOf(kind: Kind, row: Setting | Flag): ValueKind {
  if (kind === "flags") return typeof row.value === "boolean" ? "bool" : "json";
  const named = (row as Setting).kind;
  return Array.isArray(named) ? named.map(String) : named === "bool" ? "bool" : "str";
}

/** The new value from the form, of the switch's kind. */
function readValue(form: FormData, kind: ValueKind): unknown {
  if (form.get("reset") === "on") return null;
  if (kind === "bool") return form.get("value") === "on";
  const text = formText(form, "value");
  if (kind !== "json") return text;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(400, "invalid", copy.errors.badRequest, { value: [copy.errors.badRequest] });
  }
}

function ValueField({
  id,
  row,
  kind,
  error,
}: {
  id: string;
  row: Setting | Flag;
  kind: ValueKind;
  error: ApiError | null;
}) {
  if (kind === "bool") {
    return (
      <Switch name="value" defaultChecked={row.value === true}>
        {row.key}
      </Switch>
    );
  }
  return (
    <Field id={`${id}-value`} label={copy.settings.value} error={fieldError(error, "value")}>
      {Array.isArray(kind) ? (
        <Select name="value" defaultValue={String(row.value ?? "")}>
          {kind.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </Select>
      ) : kind === "json" ? (
        <Textarea name="value" rows={4} defaultValue={JSON.stringify(row.value, null, 2)} className="font-mono" />
      ) : (
        <Input name="value" defaultValue={String(row.value ?? "")} autoComplete="off" />
      )}
    </Field>
  );
}

function History({ kind, keyName }: { kind: Kind; keyName: string }) {
  const manifest = useManifest();
  const [rows, setRows] = useState<SwitchRow[] | "failed" | null>(null);
  return (
    <details
      className="basis-full"
      onToggle={(event) => {
        if (!event.currentTarget.open || rows !== null) return;
        switchHistory(kind, keyName).then(setRows, () => setRows("failed"));
      }}
    >
      <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
        {copy.settings.history} <span className="sr-only">{keyName}</span>
      </summary>
      {rows === null ? (
        <p className="m-0 pt-2 text-[15px] text-muted-foreground">{copy.common.loading}</p>
      ) : rows === "failed" ? (
        <p className="m-0 pt-2 text-[15px] text-destructive">{copy.settings.historyFailed}</p>
      ) : rows.length ? (
        <ol className="m-0 flex list-none flex-col gap-2 p-0 pt-2 text-[15px]">
          {rows.map((change, index) => (
            <li key={`${change.created}-${index}`} className="border-l-2 border-border pl-3">
              <code className="break-all">{valueText(change.value)}</code>
              <span className="block text-sm text-muted-foreground">
                {copy.settings.historyEntry(
                  staffLabel(change.changed_by, manifest.user.id),
                  formatDateTime(change.created),
                )}
                {change.effective_from !== change.created
                  ? ` · ${copy.settings.columns.effective}: ${formatDateTime(change.effective_from)}`
                  : ""}
                {change.reason ? ` · “${change.reason}”` : ""}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-0 pt-2 text-[15px] text-muted-foreground">{copy.settings.noHistory}</p>
      )}
    </details>
  );
}

function SettingRow({ kind, row }: { kind: Kind; row: Setting | Flag }) {
  const can = useCan();
  const manifest = useManifest();
  const setting = kind === "settings" ? (row as Setting) : null;
  const changing = can(setting ? setting.permission : P.flagsChange);
  const valueKind = kindOf(kind, row);
  const id = `${kind}-${row.key.replace(/[^a-z0-9_-]/gi, "_")}`;
  const source = setting?.source ?? "database";
  return (
    <li className="flex flex-col gap-3 border-b border-border py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1">
          <code className="text-[15px] font-semibold break-all">{row.key}</code>
          {setting?.label ? <span className="text-sm text-muted-foreground">{setting.label}</span> : null}
          <span className="text-[15px] break-words">{valueText(row.value)}</span>
        </div>
        <StatusChip tone={source === "environment" ? "stopped" : "moving"}>
          {labelOf(copy.settings.sources, source)}
        </StatusChip>
      </div>
      <p className="m-0 text-sm text-muted-foreground">
        {[
          setting ? copy.settings.environmentValue(valueText(setting.environment)) : "",
          row.effective_from ? `${copy.settings.columns.effective}: ${formatDateTime(row.effective_from)}` : "",
          row.changed_by ? `${copy.settings.columns.changedBy}: ${staffLabel(row.changed_by, manifest.user.id)}` : "",
          row.reason ? `“${row.reason}”` : "",
          ...(setting?.scheduled ?? []).map((next) =>
            copy.settings.scheduled(valueText(next.value), formatDateTime(String(next.effective_from))),
          ),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <div className="flex flex-wrap gap-x-6">
        {changing ? (
          <details className="group basis-full">
            <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
              {copy.settings.change} <span className="sr-only">{row.key}</span>
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
                  const body = {
                    value: readValue(form, valueKind),
                    reason: formText(form, "reason"),
                    ...(effective ? { effective_from: fromLocalInput(effective) } : {}),
                  };
                  return kind === "settings" ? changeSetting(row.key, body) : changeFlag(row.key, body);
                }}
              >
                {(error) => (
                  <>
                    <ValueField id={id} row={row} kind={valueKind} error={error} />
                    {setting ? <Checkbox name="reset">{copy.settings.backToEnvironment}</Checkbox> : null}
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
        <History kind={kind} keyName={row.key} />
      </div>
    </li>
  );
}

export function SettingsList({ kind, rows }: { kind: Kind; rows: (Setting | Flag)[] }) {
  return (
    <ul className="m-0 flex list-none flex-col border-t-[1.5px] border-foreground p-0">
      {rows.map((row) => (
        <SettingRow key={row.key} kind={kind} row={row} />
      ))}
    </ul>
  );
}
