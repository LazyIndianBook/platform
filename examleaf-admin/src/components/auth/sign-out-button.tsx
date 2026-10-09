"use client";

// Sign out from the pages before the console opens (no access, set up two-step sign-in).
import { useState } from "react";

import { signOut } from "@/components/shell/sign-out";
import { Button } from "@/components/ui/button";
import { copy } from "@/lib/copy";

export function SignOutButton({ variant = "primary" }: { variant?: "primary" | "secondary" }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant={variant}
      size="lg"
      block
      busy={busy}
      onClick={() => {
        setBusy(true);
        signOut();
      }}
    >
      {copy.common.signOut}
    </Button>
  );
}
