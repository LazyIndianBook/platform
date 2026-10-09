"use client";

// Adding a processor to the register (POST processors/): who, for what, where the data is kept, which kinds of
// personal data, and when the agreement was signed and when it ends.
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
      labels={{
        name: copy.privacy.processorName,
        purpose: copy.privacy.processorPurpose,
        country: copy.privacy.processorCountry,
        data_categories: copy.privacy.processorCategories,
        contract_signed_on: copy.privacy.processorSigned,
        contract_ends_on: copy.privacy.processorContract,
      }}
      onSubmit={(form) =>
        createProcessor({
          name: formText(form, "name"),
          purpose: formText(form, "purpose"),
          country: formText(form, "country"),
          data_categories: formText(form, "data_categories"),
          contract_signed_on: formText(form, "contract_signed_on") || null,
          contract_ends_on: formText(form, "contract_ends_on") || null,
          active: true,
          notes: "",
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
              <Input name="purpose" autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-processor-country"
              label={copy.privacy.processorCountry}
              error={fieldError(error, "country")}
            >
              <Input name="country" autoComplete="off" aria-required="true" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field
              id="new-processor-data_categories"
              label={copy.privacy.processorCategories}
              help={copy.privacy.dataCategoriesHelp}
              error={fieldError(error, "data_categories")}
            >
              <Input name="data_categories" autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-processor-contract_signed_on"
              label={copy.privacy.processorSigned}
              optional
              error={fieldError(error, "contract_signed_on")}
            >
              <Input name="contract_signed_on" type="date" />
            </Field>
            <Field
              id="new-processor-contract_ends_on"
              label={copy.privacy.processorContract}
              optional
              error={fieldError(error, "contract_ends_on")}
            >
              <Input name="contract_ends_on" type="date" />
            </Field>
          </FormGrid>
        </>
      )}
    </ActionForm>
  );
}
