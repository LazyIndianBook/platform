"use client";

// Adding a processor to the register (POST processors/): who, for what, where the data is kept, which kinds of
// personal data, and until when the agreement runs.
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { createProcessor } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function NewProcessorForm() {
  return (
    <ActionForm
      id="new-processor"
      submitLabel={copy.privacy.processorAdd}
      success={copy.privacy.processorAdded}
      labels={{ name: copy.privacy.processorName }}
      onSubmit={(form) =>
        createProcessor({
          name: formText(form, "name"),
          purpose: formText(form, "purpose"),
          country: formText(form, "country"),
          data_categories: formText(form, "data_categories")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          contract_until: formText(form, "contract_until") || null,
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-processor-name" label={copy.privacy.processorName} error={fieldError(error, "name")}>
              <Input name="name" autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-processor-purpose"
              label={copy.privacy.processorPurpose}
              error={fieldError(error, "purpose")}
            >
              <Input name="purpose" autoComplete="off" />
            </Field>
            <Field
              id="new-processor-country"
              label={copy.privacy.processorCountry}
              error={fieldError(error, "country")}
            >
              <Input name="country" autoComplete="off" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field
              id="new-processor-data_categories"
              label={copy.privacy.processorCategories}
              help={copy.privacy.dataCategoriesHelp}
              error={fieldError(error, "data_categories")}
            >
              <Input name="data_categories" autoComplete="off" />
            </Field>
            <Field
              id="new-processor-contract_until"
              label={copy.privacy.processorContract}
              optional
              error={fieldError(error, "contract_until")}
            >
              <Input name="contract_until" type="date" />
            </Field>
          </FormGrid>
        </>
      )}
    </ActionForm>
  );
}
