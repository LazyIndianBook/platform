"use client";

// Maintenance mode (POST system/maintenance/: on or off, the banner visitors see, and a reason), which may ask to
// confirm it's you. The console itself stays open while it is on.
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { setMaintenance } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function MaintenanceForm({ on, banner }: { on: boolean; banner: string }) {
  const id = `maintenance-${on ? "off" : "on"}`;
  return (
    <ActionForm
      id={id}
      submitLabel={on ? copy.system.turnOff : copy.system.turnOn}
      variant={on ? "primary" : "destructive"}
      success={copy.system.maintenanceSaved}
      labels={{ banner: copy.system.banner, reason: copy.common.reason }}
      onSubmit={(form) =>
        setMaintenance({ on: !on, banner: on ? "" : formText(form, "banner"), reason: formText(form, "reason") })
      }
    >
      {(error) => (
        <>
          {on ? null : (
            <Field id={`${id}-banner`} label={copy.system.banner} error={fieldError(error, "banner")}>
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
