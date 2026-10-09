"use client";

// Copies a value to the clipboard (a hash, a new key's secret, a drafted reply) and says so in a toast.
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { copy } from "@/lib/copy";

export function CopyButton({
  value,
  label = copy.common.copy,
  what,
}: {
  value: string;
  label?: string;
  what?: string;
}) {
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          toast.success(copy.common.copied);
        } catch {
          // no clipboard (an old browser, a denied permission): the value is on the page to select by hand
        }
      }}
    >
      {label}
      {what ? (
        <>
          {" "}
          <span className="sr-only">{what}</span>
        </>
      ) : null}
    </Button>
  );
}
