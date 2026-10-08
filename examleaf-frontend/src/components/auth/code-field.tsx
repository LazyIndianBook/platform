"use client";

// The six boxes of a code, with their own error: the boards draw no label above them (the lead sentence says what to
// type), so the field is named by the boxes' aria-label ("6-digit code") and its error sits under them.
import { FieldError } from "@/components/ui/field";
import { OtpInput } from "@/components/ui/input-otp";

export function CodeField({
  id,
  value,
  onChange,
  error,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  error?: string[] | null;
}) {
  const message = error?.join(" ");
  return (
    <div className="flex flex-col gap-1.5">
      <OtpInput
        id={id}
        value={value}
        onChange={onChange}
        autoFocus
        required
        aria-invalid={message ? true : undefined}
        aria-describedby={message ? `${id}-error` : undefined}
      />
      {message ? <FieldError id={`${id}-error`}>{message}</FieldError> : null}
    </div>
  );
}
