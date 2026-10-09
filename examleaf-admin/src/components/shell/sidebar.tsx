"use client";

// The sidebar: only the modules the manifest opens (lib/modules.ts), under their groups, in the plan's order. The
// current page is ink on white with the navy bar at its edge (aria-current); the planned modules say "soon"; the
// business modules are links out to ERPNext (a new tab, said in words), drawn only when its address is set.
import { cn } from "cn";
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useManifest } from "@/components/shell/manifest";
import { copy } from "@/lib/copy";
import { groupedModules, moduleHref, MODULES } from "@/lib/modules";
import { ERP_URL } from "@/lib/site";

/** The module the path belongs to: the longest href that starts it ("/people/access-review/" is Access review). */
export function currentModule(pathname: string): string | null {
  const match = MODULES.filter(
    (module) => !module.erp && (module.href === "/" ? pathname === "/" : pathname.startsWith(module.href)),
  ).sort((a, b) => b.href.length - a.href.length)[0];
  return match?.key ?? null;
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const manifest = useManifest();
  const pathname = usePathname();
  const current = currentModule(pathname);
  const groups = groupedModules(manifest, ERP_URL);

  return (
    <nav aria-label={copy.shell.modules} className="flex flex-col gap-5 px-3 pt-4 pb-10">
      {groups.map(({ group, modules }) => (
        <div key={group} className="flex flex-col gap-1">
          <h2 className="m-0 px-3 label-mono text-[12px] uppercase">{copy.nav.groups[group]}</h2>
          <ul className="m-0 flex list-none flex-col p-0">
            {modules.map((module) => {
              const label = copy.nav.modules[module.key];
              const linkClass = cn(
                "flex min-h-11 items-center justify-between gap-2 rounded-[3px] px-3 text-[15px] font-semibold text-foreground no-underline",
                "hover:bg-secondary-hover hover:text-foreground hover:no-underline",
              );
              if (module.erp) {
                return (
                  <li key={module.key}>
                    <a
                      href={moduleHref(module, ERP_URL)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={linkClass}
                    >
                      <span>
                        {label}
                        <span className="sr-only">
                          {" "}
                          ({copy.shell.erpOpens}, {copy.common.opensElsewhere})
                        </span>
                      </span>
                      <ExternalLink aria-hidden="true" className="size-4 text-muted-foreground" />
                    </a>
                  </li>
                );
              }
              const here = current === module.key;
              return (
                <li key={module.key}>
                  <Link
                    href={module.href}
                    aria-current={here ? "page" : undefined}
                    onClick={onNavigate}
                    className={cn(linkClass, here && "bg-card shadow-[inset_3px_0_0_var(--primary)]")}
                  >
                    <span>{label}</span>
                    {module.soon ? (
                      <span className="font-mono text-[11px] font-medium tracking-[0.04em] text-muted-foreground uppercase">
                        {copy.shell.soon}
                      </span>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
