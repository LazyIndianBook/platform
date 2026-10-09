"use client";

// A small form that does one thing through the staff API (grant a role, change a setting, log a request): its fields,
// one submit that sends once (busy), the error summary (the API's field errors beside their fields, an approval
// that was asked for instead), a draft kept while typing, and after success a short toast and a fresh render of the
// page from the server. The fields are the children, given the current error; their ids are `${id}-${name}`.
// With `saveBar` (plan 5.0: a contextual save bar): once something is typed, a bar at the foot of the window offers
// Save and Discard, the page keeps the bar's height clear for the focus (WCAG 2.4.11), and leaving the page, by a
// link or by closing it, asks first.
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import type { ApiError } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

import { ErrorSummary } from "./error-summary";
import { useAction } from "./use-action";
import { useDraftForm } from "./use-draft";

type ActionFormProps = {
  /** The draft's key and the fields' id prefix: unique on the page. */
  id: string;
  submitLabel: string;
  /** Sends the form; what it returns goes to onDone. */
  onSubmit: (form: FormData) => Promise<unknown>;
  /** The toast after it worked (three words or fewer). */
  success?: string;
  onDone?: (result: unknown) => void;
  labels?: Record<string, string>;
  variant?: "primary" | "secondary" | "destructive";
  className?: string;
  /** Save and Discard in a bar at the foot of the window once something is typed, and a warning before leaving. */
  saveBar?: boolean;
  children: (error: ApiError | null) => React.ReactNode;
};

/** While `dirty`: leaving the page asks first (closing or reloading it: the browser's own question; a link of the
 *  console: ours), and the page keeps the save bar's height clear of the focus. */
export function useLeaveWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const onUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const onClick = (event: MouseEvent) => {
      const link = (event.target as HTMLElement | null)?.closest?.("a[href]");
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return;
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      if (link.href.split("#")[0] === window.location.href.split("#")[0]) return; // the same page: nothing is lost
      if (!window.confirm(copy.common.leaveWarning)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const root = document.documentElement;
    const padding = root.style.scrollPaddingBottom;
    root.style.scrollPaddingBottom = "6rem";
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      root.style.scrollPaddingBottom = padding;
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);
}

export function ActionForm({
  id,
  submitLabel,
  onSubmit,
  success,
  onDone,
  labels,
  variant = "primary",
  className,
  saveBar = false,
  children,
}: ActionFormProps) {
  const router = useRouter();
  // a draft put back after a session ended counts as unsaved (useDraftForm fills the fields in after hydration)
  const [dirty, setDirty] = useState(false);
  const { ref, save, clear } = useDraftForm(id, () => setDirty(true));
  const { run, busy, error, setError } = useAction();
  useLeaveWarning(saveBar && dirty);

  const discard = () => {
    const form = ref.current;
    if (form) HTMLFormElement.prototype.reset.call(form);
    clear();
    setError(null);
    setDirty(false);
  };

  return (
    <form
      ref={ref}
      onInput={() => {
        save();
        if (saveBar) setDirty(true);
      }}
      noValidate
      className={className ?? "flex max-w-[40rem] flex-col gap-4"}
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        let result: unknown;
        const ok = await run(async () => {
          result = await onSubmit(new FormData(form));
        });
        if (!ok) return;
        clear();
        setDirty(false);
        // the form's own reset: a field named "reset" (a setting's "back to the environment's") hides form.reset
        HTMLFormElement.prototype.reset.call(form);
        if (success) toast.success(success);
        onDone?.(result);
        router.refresh();
      }}
    >
      <ErrorSummary error={error} labels={labels} idPrefix={`${id}-`} />
      {children(error)}
      {saveBar ? (
        dirty ? (
          <div
            role="region"
            aria-label={copy.common.unsaved}
            className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center justify-between gap-3 border-t-[1.5px] border-foreground bg-card px-4 py-3"
          >
            <p className="m-0 text-[15px] font-semibold">
              {copy.common.unsaved}
              <span className="font-normal text-muted-foreground"> {copy.common.unsavedText}</span>
            </p>
            <div className="flex flex-wrap gap-2.5">
              <Button type="button" variant="secondary" onClick={discard} disabled={busy}>
                {copy.common.discard}
              </Button>
              <Button type="submit" variant={variant} busy={busy}>
                {submitLabel}
              </Button>
            </div>
          </div>
        ) : null
      ) : (
        <div>
          <Button type="submit" variant={variant} busy={busy}>
            {submitLabel}
          </Button>
        </div>
      )}
    </form>
  );
}

/** A text field of a FormData, trimmed. */
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
