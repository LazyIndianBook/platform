"use client";

// API keys for integrations: making one (POST api-keys/: a name, its view permissions, an end date at most a year away,
// optionally the addresses it may come from) shows the whole key this once (`key`), with Copy and a plain warning,
// until the person says they stored it; revoking one asks for its name to be typed (POST api-keys/{id}/revoke/). Both
// may ask to confirm it's you.
import { useState } from "react";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { CopyButton } from "@/components/data/copy-button";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { type ApiKey, createApiKey, revokeApiKey } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const list = (text: string) =>
  text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

export function RevokeKey({ apiKey }: { apiKey: ApiKey }) {
  return (
    <ConfirmTyped
      label={apiKey.name}
      triggerLabel={
        <>
          {copy.apiKeys.revoke} <span className="sr-only">{apiKey.name}</span>
        </>
      }
      triggerVariant="destructive"
      title={copy.apiKeys.revokeTitle(apiKey.name)}
      text={copy.apiKeys.revokeText}
      confirmLabel={copy.apiKeys.revoke}
      success={copy.apiKeys.revoked}
      onConfirm={() => revokeApiKey(apiKey.id)}
    />
  );
}

export function NewKey({ latest }: { latest: string }) {
  const [made, setMade] = useState<{ name: string; key: string } | null>(null);
  if (made) {
    return (
      <Alert variant="warning" title={copy.apiKeys.secretTitle} role="alert">
        <p>{copy.apiKeys.secretText}</p>
        <p className="my-2 rounded-[3px] border border-border bg-card p-3 font-mono text-[14px] break-all select-all">
          {made.key}
        </p>
        <p className="flex flex-wrap gap-2.5">
          <CopyButton value={made.key} what={made.name} />
          <Button size="sm" onClick={() => setMade(null)}>
            {copy.apiKeys.secretStored}
          </Button>
        </p>
      </Alert>
    );
  }
  return (
    <ActionForm
      id="new-key"
      submitLabel={copy.apiKeys.createButton}
      labels={{
        name: copy.apiKeys.name,
        scopes: copy.apiKeys.scopes,
        expires_at: copy.apiKeys.expires,
        allowed_ips: copy.apiKeys.allowedIps,
      }}
      onSubmit={(form) => {
        const ends = formText(form, "expires_at");
        return createApiKey({
          name: formText(form, "name"),
          scopes: list(formText(form, "scopes")),
          allowed_ips: list(formText(form, "allowed_ips")),
          ...(ends ? { expires_at: `${ends}T23:59:59+05:30` } : {}),
        });
      }}
      onDone={(result) => {
        const answer = result as ApiKey;
        if (answer.key) setMade({ name: answer.name, key: answer.key });
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field
              id="new-key-name"
              label={copy.apiKeys.name}
              help={copy.apiKeys.nameHelp}
              error={fieldError(error, "name")}
            >
              <Input name="name" autoComplete="off" aria-required="true" maxLength={80} />
            </Field>
            <Field
              id="new-key-expires_at"
              label={copy.apiKeys.expires}
              optional
              help={copy.apiKeys.expiresHelp}
              error={fieldError(error, "expires_at")}
            >
              <Input name="expires_at" type="date" max={latest} />
            </Field>
          </FormGrid>
          <Field
            id="new-key-scopes"
            label={copy.apiKeys.scopes}
            help={copy.apiKeys.scopesHelp}
            error={fieldError(error, "scopes")}
          >
            <Input name="scopes" autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
          <Field
            id="new-key-allowed_ips"
            label={copy.apiKeys.allowedIps}
            optional
            help={copy.apiKeys.allowedIpsHelp}
            error={fieldError(error, "allowed_ips")}
          >
            <Input name="allowed_ips" autoComplete="off" className="font-mono" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
