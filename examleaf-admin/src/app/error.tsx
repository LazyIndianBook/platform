"use client";

// A page outside the console's frame that failed (sign-in, or the panel's layout itself, when the session check
// could not reach Django).
import { AuthFrame } from "@/components/auth/auth-frame";
import { ErrorView } from "@/components/shell/error-view";

export default function RootError(props: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <AuthFrame>
      <ErrorView {...props} />
    </AuthFrame>
  );
}
