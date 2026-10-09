// One record (a customer, a staff member, a change request, a data request): the header with its status chip and
// primary actions, tabs for its parts (links: the server renders one part at a time), its content beside its
// timeline (audit events and notes; under it on a phone), and the Danger section last, for what cannot be undone.
import { cn } from "cn";
import Link from "next/link";

import { PageHeader } from "@/components/shell/page-header";
import { copy } from "@/lib/copy";

export type RecordTab = { key: string; label: string; href: string };

type RecordPageProps = {
  eyebrow?: string;
  title: React.ReactNode;
  lead?: React.ReactNode;
  back?: { href: string; label: string };
  status?: React.ReactNode;
  actions?: React.ReactNode;
  tabs?: RecordTab[];
  current?: string;
  /** The record's timeline (EventTimeline), beside the content. */
  timeline?: React.ReactNode;
  timelineLabel?: string;
  /** The Danger section's content: actions that cannot be undone. */
  danger?: React.ReactNode;
  dangerTitle?: string;
  children: React.ReactNode;
};

export function RecordPage({
  eyebrow,
  title,
  lead,
  back,
  status,
  actions,
  tabs,
  current,
  timeline,
  timelineLabel,
  danger,
  dangerTitle,
  children,
}: RecordPageProps) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} lead={lead} back={back} status={status} actions={actions} />
      {tabs?.length ? (
        <nav aria-label={copy.common.details} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
          <ul className="m-0 flex list-none p-0">
            {tabs.map((tab) => (
              <li key={tab.key}>
                <Link
                  href={tab.href}
                  aria-current={tab.key === current ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                    tab.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
                  )}
                >
                  {tab.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      <div className={cn("grid gap-8", timeline && "min-[1180px]:grid-cols-[minmax(0,1fr)_320px]")}>
        <div className="flex min-w-0 flex-col gap-8">{children}</div>
        {timeline ? (
          <aside
            aria-label={timelineLabel}
            className="min-w-0 border-t border-border pt-6 min-[1180px]:border-t-0 min-[1180px]:border-l min-[1180px]:pt-0 min-[1180px]:pl-6"
          >
            {timelineLabel ? <h2 className="m-0 mb-4 font-head text-xl leading-tight">{timelineLabel}</h2> : null}
            {timeline}
          </aside>
        ) : null}
      </div>
      {danger ? (
        <section
          aria-labelledby="danger-title"
          className="mt-10 flex flex-col gap-4 border-[1.5px] border-destructive/40 bg-card p-5"
        >
          <h2 id="danger-title" className="m-0 font-head text-xl leading-tight text-destructive">
            {dangerTitle ?? copy.users.danger}
          </h2>
          {danger}
        </section>
      ) : null}
    </>
  );
}

/** A record's facts: a definition list, two columns from 640 px. */
export function Facts({ items }: { items: { label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="m-0 grid gap-x-8 gap-y-3 min-[640px]:grid-cols-[minmax(10rem,auto)_minmax(0,1fr)]">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-sm font-semibold text-muted-foreground min-[640px]:pt-0.5">{item.label}</dt>
          <dd className="m-0 min-w-0 text-[15px] break-words">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** One danger action: what it does in words, its button at the right. */
export function DangerRow({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-border pt-4 first-of-type:border-t-0 first-of-type:pt-0">
      <div className="flex max-w-[48ch] flex-col gap-0.5">
        <p className="m-0 font-semibold">{title}</p>
        <p className="m-0 text-[15px] text-muted-foreground">{text}</p>
      </div>
      {children}
    </div>
  );
}
