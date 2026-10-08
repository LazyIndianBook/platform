"use client";

// .otp, Direction A (Components board, 04): six 44×54 boxes in Plex Mono 500 24 over one real input (input-otp), so
// Android's SMS autofill, the numeric keypad, a pasted code and Backspace all work, and screen readers hear one field.
// A paste keeps only its digits and a whole code replaces what was there, so "482 913" or "Your code: 482913" fills
// all six. The box the next digit goes into is navy inside the focus ring; an error is the error red; disabled is
// paper 2. On a phone the six boxes share the width (320 px too, 56 px each at most); from the desktop layout up they
// are 44 px wide. Its value is posted as `name` (default "code").
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

const digitsOf = (pasted: string) => pasted.replace(/\D/g, "").slice(0, 6);

function OtpInput({ name = "code", value, onChange, ...props }: OtpInputProps) {
  const [inner, setInner] = React.useState("");
  return (
    <OTPInput
      name={name}
      maxLength={6}
      pattern={REGEXP_ONLY_DIGITS}
      pasteTransformer={digitsOf}
      onPasteCapture={(event: React.ClipboardEvent<HTMLInputElement>) => {
        // a whole code replaces what was typed, wherever the caret is (input-otp inserts at the caret)
        const input = event.currentTarget;
        if (digitsOf(event.clipboardData.getData("text/plain")).length === 6)
          input.setSelectionRange(0, input.value.length);
      }}
      inputMode="numeric"
      autoComplete="one-time-code"
      aria-label="6-digit code"
      value={value ?? inner}
      onChange={onChange ?? setInner}
      containerClassName="group/otp flex w-full items-center gap-1.5 nav:w-auto nav:gap-2"
      render={({ slots }) =>
        slots.map((slot, index) => (
          <div
            key={index}
            data-slot="otp-box"
            data-active={slot.isActive || undefined}
            className={cn(
              "relative flex h-[54px] min-w-0 max-w-14 flex-1 items-center justify-center rounded-lg border-[1.5px] border-input bg-card nav:w-11 nav:max-w-none nav:flex-none",
              "font-mono text-2xl leading-none font-medium text-foreground",
              props["aria-invalid"] && "border-destructive shadow-[inset_0_0_0_0.5px_var(--destructive)]",
              "data-active:border-primary data-active:outline-2 data-active:outline-offset-2 data-active:outline-ring",
              "group-has-disabled/otp:border-[#c9ccd2] group-has-disabled/otp:bg-paper-2 group-has-disabled/otp:text-input",
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
