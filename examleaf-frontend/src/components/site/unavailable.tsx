// The honest state when Django cannot be reached (or answers with an error) for a whole page: rendering it throws
// unavailableError(), so the answer is a server error and error.tsx says "ExamLeaf cannot be reached just now" with
// Try again (security review S5: never a 200, an indexable page, in place of the real one). Never stale or made-up
// data in its place. The props name the page for the call sites; the words are error.tsx's.
import { unavailableError } from "@/lib/api/errors";

export function Unavailable(props: { retry?: string; what?: string }): never {
  void props;
  throw unavailableError();
}
