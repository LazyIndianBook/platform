// A record's versions (GET …/history/ of a product, a coupon, an offer or a shipping rate), newest first: when, who,
// why (a price's change request names itself), and what each changed against the version before it, a field's
// value before and after. The prices are among them: the website's prior price is read from these.
import Link from "next/link";

import type { CatalogueVersion } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { shown } from "./shared";

export function Versions({
  versions,
  labels,
  older,
}: {
  versions: CatalogueVersion[];
  /** The fields' words, by name; a name without one is shown as it is. */
  labels: Record<string, string>;
  /** The link to older versions, when there are more. */
  older?: string | null;
}) {
  if (!versions.length) return <p className="m-0 text-muted-foreground">{copy.catalogue.noVersions}</p>;
  return (
    <div className="flex flex-col gap-4">
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {versions.map((version) => (
          <li key={version.id} className="rounded-lg border border-border bg-card p-4">
            <p className="m-0 font-semibold">
              {formatDateTime(version.at)} · {version.by_name || copy.catalogue.bySite}
            </p>
            {version.reason ? <p className="m-0 mt-1 text-[15px] text-muted-foreground">“{version.reason}”</p> : null}
            {version.type === "+" ? (
              <p className="m-0 mt-2 text-[15px]">{copy.catalogue.firstVersion}</p>
            ) : version.changes.length ? (
              <dl className="m-0 mt-2 grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[15px] max-sm:grid-cols-1">
                {version.changes.map((change) => (
                  <div key={change.field} className="contents">
                    <dt className="font-semibold">{labelOf(labels, change.field)}</dt>
                    <dd className="m-0 break-words">
                      <span className="text-muted-foreground line-through">{shown(change.before)}</span>{" "}
                      <span aria-hidden="true">→</span>
                      <span className="sr-only">{copy.catalogue.becomes}</span> {shown(change.after)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="m-0 mt-2 text-[15px] text-muted-foreground">{copy.catalogue.noFieldChanged}</p>
            )}
          </li>
        ))}
      </ol>
      {older ? (
        <p className="m-0">
          <Link href={older} className="inline-flex min-h-11 items-center font-semibold">
            {copy.catalogue.olderVersions}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
