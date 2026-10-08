"use client";

// Log out: allauth.headless ends the session (DELETE /_allauth/browser/v1/auth/session), then a fresh home page.
import { LogOut } from "lucide-react";
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
      onClick={async () => {
        setBusy(true);
        try {
          await auth.logout();
        } finally {
          // a full load: the header, the cart and every layout read the ended session
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.assign("/");
        }
      }}
    >
      <LogOut aria-hidden="true" />
      <span>Log out</span>
    </Button>
  );
}
