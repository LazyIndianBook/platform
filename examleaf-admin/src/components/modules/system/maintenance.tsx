"use client";

// Maintenance mode through the site's switches (PUT settings/MAINTENANCE_BANNER/, then PUT settings/MAINTENANCE_MODE/,
// staff.toggle_maintenance), each with the reason, and each audited; it may ask to confirm it's you. The console itself
// stays open while it is on. Also: asking Razorpay what became of an order's payment (POST system/reconcile/).
import { useState } from "react";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { changeSetting, reconcileOrder } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function MaintenanceForm({ on, banner }: { on: boolean; banner: string }) {
  const id = `maintenance-${on ? "off" : "on"}`;
  return (
    <ActionForm
      id={id}
      submitLabel={on ? copy.system.turnOff : copy.system.turnOn}
      variant={on ? "primary" : "destructive"}
      success={copy.system.maintenanceSaved}
      labels={{ value: copy.system.banner, reason: copy.common.reason }}
      onSubmit={async (form) => {
        const reason = formText(form, "reason");
        const text = formText(form, "banner");
        if (!on && text !== banner) await changeSetting("MAINTENANCE_BANNER", { value: text, reason });
        return changeSetting("MAINTENANCE_MODE", { value: !on, reason });
      }}
    >
      {(error) => (
        <>
          {on ? null : (
            <Field id={`${id}-banner`} label={copy.system.banner} error={fieldError(error, "value")}>
              <Input name="banner" defaultValue={banner} autoComplete="off" maxLength={200} />
            </Field>
          )}
          <Field
            id={`${id}-reason`}
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function ReconcileForm() {
  const [answer, setAnswer] = useState<{ order: string; paid: boolean | null } | null>(null);
  return (
    <div className="flex flex-col gap-3">
      <ActionForm
        id="reconcile"
        submitLabel={copy.system.reconcileButton}
        variant="secondary"
        labels={{ order: copy.system.reconcileOrder }}
        onSubmit={(form) => reconcileOrder(formText(form, "order"))}
        onDone={(result) => setAnswer(result as { order: string; paid: boolean | null })}
      >
        {(error) => (
          <Field id="reconcile-order" label={copy.system.reconcileOrder} error={fieldError(error, "order")}>
            <Input name="order" autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
        )}
      </ActionForm>
      {answer ? (
        <Alert variant={answer.paid ? "success" : "info"} title={copy.system.reconciled(answer.order, answer.paid)} />
      ) : null}
    </div>
  );
}
