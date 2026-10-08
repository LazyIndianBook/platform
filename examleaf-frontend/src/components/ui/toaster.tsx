"use client";

// The toast region (components.md, .toast): top right under the header on desktop, at the bottom on phones (where
// globals.css keeps a focused field clear of it), a polite live region (sonner's), a Dismiss button, no auto-dismiss:
// a toast stays until dismissed or the next page. Call toast.success("…") / toast.error("…") from "sonner".
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { toast, Toaster as Sonner } from "sonner";

const PHONE = "(max-width: 899.98px)";

function subscribe(callback: () => void) {
  const query = window.matchMedia(PHONE);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

function Toaster() {
  const phone = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(PHONE).matches,
    () => false,
  );
  const pathname = usePathname();
  useEffect(() => {
    toast.dismiss(); // "until the next page"
  }, [pathname]);

  return (
    <Sonner
      position={phone ? "bottom-center" : "top-right"}
      offset={{ top: 80, right: 24, bottom: 16 }}
      mobileOffset={{ bottom: 16, left: 16, right: 16 }}
      duration={Infinity}
      closeButton
      containerAriaLabel="Messages"
      icons={{
        success: <CircleCheck aria-hidden="true" className="size-[22px] text-success-fg" />,
        info: <Info aria-hidden="true" className="size-[22px] text-info-fg" />,
        warning: <TriangleAlert aria-hidden="true" className="size-[22px] text-warning-fg" />,
        error: <CircleAlert aria-hidden="true" className="size-[22px] text-error-fg" />,
      }}
      toastOptions={{
        closeButtonAriaLabel: "Dismiss",
        classNames: {
          toast: "!bg-card !text-foreground !border-border !shadow-card",
          closeButton: "!bg-card !border-border !text-primary",
        },
      }}
    />
  );
}

export { Toaster };
