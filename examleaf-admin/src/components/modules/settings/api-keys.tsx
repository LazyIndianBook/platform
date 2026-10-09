"use client";

// API keys for integrations: making one (POST api-keys/: a name, its scopes, an end date at most a year away) shows its
// secret this once, with Copy and a plain warning, until the person says they stored it; revoking one asks for its
// name to be typed (POST api-keys/{id}/revoke/). Both may ask to confirm it's you.
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
  const [made, setMade] = useState<{ name: string; secret: string } | null>(null);
  if (made) {
    return (
      <Alert variant="warning" title={copy.apiKeys.secretTitle} role="alert">
        <p>{copy.apiKeys.secretText}</p>
        <p className="my-2 rounded-[3px] border border-border bg-card p-3 font-mono text-[14px] break-all select-all">
          {made.secret}
        </p>
        <p className="flex flex-wrap gap-2.5">
          <CopyButton value={made.secret} what={made.name} />
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
      labels={{ name: copy.apiKeys.name, scopes: copy.apiKeys.scopes, expires_at: copy.apiKeys.expires }}
      onSubmit={(form) =>
        createApiKey({
          name: formText(form, "name"),
          scopes: formText(form, "scopes")
            .split(",")
            .map((scope) => scope.trim())
            .filter(Boolean),
          expires_at: formText(form, "expires_at"),
        })
      }
      onDone={(result) => {
        const answer = result as { key: ApiKey; secret: string };
        setMade({ name: answer.key.name, secret: answer.secret });
      }}
    >
      {(error) => (
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
            id="new-key-scopes"
            label={copy.apiKeys.scopes}
            help={copy.apiKeys.scopesHelp}
            error={fieldError(error, "scopes")}
          >
            <Input name="scopes" autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
          <Field
            id="new-key-expires_at"
            label={copy.apiKeys.expires}
            help={copy.apiKeys.expiresHelp}
            error={fieldError(error, "expires_at")}
          >
            <Input name="expires_at" type="date" max={latest} aria-required="true" />
          </Field>
        </FormGrid>
      )}
    </ActionForm>
  );
}
