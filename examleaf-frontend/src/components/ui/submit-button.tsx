"use client";

// A form's submit button that turns busy while its server action runs (the form still works without script).
import { useFormStatus } from "react-dom";

import { Button } from "./button";

export function SubmitButton(props: React.ComponentProps<typeof Button>) {
  const { pending } = useFormStatus();
  return <Button type="submit" busy={pending} {...props} />;
}
