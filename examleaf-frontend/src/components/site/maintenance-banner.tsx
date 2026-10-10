// The maintenance band above every page while the panel's MAINTENANCE_MODE is on (`maintenance` of GET config/):
// the banner's text from the panel, or a plain line when none was set. The site stays open: nothing here closes a
// page or a form, and the console (its own host) never shows it.
import { Info } from "lucide-react";

import type { SiteConfig } from "@/lib/api/config";

export const MAINTENANCE_DEFAULT = "We are doing some maintenance: parts of the site may not work for a short while.";

export function MaintenanceBanner({ maintenance }: { maintenance: SiteConfig["maintenance"] | null | undefined }) {
  if (!maintenance?.on) return null;
  return (
    <section aria-label="Maintenance" className="border-b border-info-line bg-info-bg">
      <div className="mx-auto flex w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] flex-wrap items-center gap-x-4 gap-y-2 px-(--gutter) py-2.5 nav:px-10">
        <Info aria-hidden="true" className="icon-filled size-6 shrink-0 text-info-fg" />
        <p className="m-0 min-w-0 flex-1 text-[15px] leading-snug text-foreground">
          {maintenance.banner?.trim() || MAINTENANCE_DEFAULT}
        </p>
      </div>
    </section>
  );
}
