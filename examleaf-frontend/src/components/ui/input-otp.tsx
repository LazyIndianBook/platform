"use client";

// .otp: six 48×56 boxes (Poppins 700 24) over one real input (input-otp), so Android's SMS autofill, a pasted code
// and Backspace all work, and screen readers hear one field. Its value is posted as `name` (default "code").
import { cn } from "cn";
import { OTPInput, REGEXP_ONLY_DIGITS } from "input-otp";
import * as React from "react";

type OtpInputProps = {
  id?: string;
  name?: string;
  value?: string;
  onChange?: (value: string) => void;
  onComplete?: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  required?: boolean;
};

function OtpInput({ name = "code", value, onChange, ...props }: OtpInputProps) {
  const [inner, setInner] = React.useState("");
  return (
    <OTPInput
      name={name}
      maxLength={6}
      pattern={REGEXP_ONLY_DIGITS}
      inputMode="numeric"
      autoComplete="one-time-code"
      aria-label="6-digit code"
      value={value ?? inner}
      onChange={onChange ?? setInner}
      containerClassName="flex items-center gap-2 has-disabled:opacity-55"
      render={({ slots }) =>
        slots.map((slot, index) => (
          <div
            key={index}
            data-active={slot.isActive || undefined}
            className={cn(
              "relative flex h-14 w-12 items-center justify-center rounded-lg border-[1.5px] border-input bg-card",
              "font-head text-2xl font-bold text-foreground",
              "data-active:outline-2 data-active:outline-offset-2 data-active:outline-ring",
              props["aria-invalid"] && "border-destructive",
            )}
          >
            {slot.char}
            {slot.hasFakeCaret ? <span aria-hidden="true" className="h-7 w-px bg-foreground" /> : null}
          </div>
        ))
      }
      {...props}
    />
  );
}

export { OtpInput };
