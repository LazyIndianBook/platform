// An address the console does not have, outside its frame (nothing is known about the session here).
import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth/auth-frame";
import { NotFoundView } from "@/components/shell/not-found-view";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.errors.notFoundTitle };

export default function NotFound() {
  return (
    <AuthFrame>
      <NotFoundView />
    </AuthFrame>
  );
}
