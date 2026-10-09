// What a page or a section says when the API did not give it its data: in the API's words where it gave some (a
// refusal by role or scope), else the console's (the server cannot be reached, its answer was not understood). Never
// stale or invented data in its place. A 401 never gets here: the page sends the person to sign in first.
import { Alert } from "@/components/ui/alert";
import type { ApiError } from "@/lib/api/errors";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";

export function Problem({ error, what }: { error: ApiError; what?: string }) {
  const title =
    error.code === "impersonating"
      ? copy.errors.impersonatingTitle
      : error.status === 403
        ? copy.problem.noAccessTitle
        : error.code === "bad_response"
          ? copy.problem.badResponseTitle
          : error.status === 429
            ? copy.problem.throttledTitle
            : error.unavailable
              ? copy.problem.unavailableTitle
              : copy.problem.failedTitle;
  const text =
    error.status === 429 && error.retryAt !== null
      ? copy.errors.throttledUntil(formatTime(error.retryAt))
      : error.code === "impersonating"
        ? copy.errors.impersonating
        : error.message;
  return (
    <Alert variant={error.status === 403 ? "warning" : "error"} title={what ? `${what}: ${title}` : title}>
      <p>{text}</p>
    </Alert>
  );
}
