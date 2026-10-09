"use client";

// Log out: allauth.headless ends the session (DELETE /_allauth/browser/v1/auth/session), then a fresh home page. The
// ink button of the Logout board (navy is for the actions that go forward).
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth/headless";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="lg"
      block
      busy={busy}
      className="border-foreground bg-foreground text-background hover:border-primary hover:bg-primary hover:text-primary-foreground"
      onClick={async () => {
        setBusy(true);
        try {
          await auth.logout();
        } catch {
          // no answer: home all the same; the session ends at its own limits
        } finally {
          // a full load: the header, the cart and every layout read the ended session
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.assign("/");
        }
      }}
    >
      Log out
    </Button>
  );
}
