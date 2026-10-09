"use client";

// A panel page that failed while rendering: inside the console's frame, so the navigation stays.
import { ErrorView } from "@/components/shell/error-view";

export default function PanelError(props: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorView {...props} />;
}
