// Every signed-in page of the console: the session manifest (GET session/, with the person's cookies) decides the
// frame (which modules, the inbox count, the impersonation banner, the idle limit). Signed out, the person goes to
// sign in and back; staff without two-step sign-in, to set it up; anyone else, to "no access" (lib/auth/session.ts).
// Each page asks again for itself (requireStaff, cached per request): a layout is not rendered again on a client-side
// navigation.
import { headers } from "next/headers";

import { ManifestProvider } from "@/components/shell/manifest";
import { Shell } from "@/components/shell/shell";
import { requestTime } from "@/lib/api/page";
import { staffTransport } from "@/lib/api/server";
import { inboxCounts } from "@/lib/api/staff";
import { requireStaff } from "@/lib/auth/session";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const path = (await headers()).get("x-pathname") ?? "/";
  const transport = await staffTransport();
  const [manifest, inbox] = await Promise.all([requireStaff(path), inboxCounts(transport).catch(() => null)]);
  return (
    <ManifestProvider manifest={manifest}>
      <Shell inbox={inbox} now={requestTime()}>
        {children}
      </Shell>
    </ManifestProvider>
  );
}
