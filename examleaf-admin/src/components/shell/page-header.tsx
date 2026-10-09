// The head of every page of the console: where it sits (a back link), its title in the serif's display cut at a
// console size (not the public site's 56 px), one line of what it is for, and its actions at the right (under the
// title on a phone).
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export function PageHeader({
  title,
  lead,
  back,
  eyebrow,
  status,
  actions,
}: {
  title: React.ReactNode;
  lead?: React.ReactNode;
  back?: { href: string; label: string };
  eyebrow?: string;
  status?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-border pb-5">
      <div className="flex min-w-0 flex-col gap-1.5 [&>*]:m-0">
        {back ? (
          <Link
            href={back.href}
            className="inline-flex min-h-11 items-center gap-1.5 self-start text-[15px] font-semibold no-underline hover:underline"
          >
            <ArrowLeft aria-hidden="true" className="size-4" />
            {back.label}
          </Link>
        ) : null}
        {eyebrow ? <p className="label-mono uppercase">{eyebrow}</p> : null}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="m-0 text-[clamp(24px,3vw,30px)] leading-tight tracking-[-0.01em] break-words">{title}</h1>
          {status}
        </div>
        {lead ? <p className="max-w-[60ch] text-[15px] leading-relaxed text-muted-foreground">{lead}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2.5">{actions}</div> : null}
    </header>
  );
}

/** A titled part of a page: the h2 in the serif's text cut, then its content. */
export function Section({
  title,
  lead,
  actions,
  children,
  id,
  className,
}: {
  title: string;
  lead?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <section aria-labelledby={id ? `${id}-title` : undefined} id={id} className={className ?? "flex flex-col gap-3"}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <h2 id={id ? `${id}-title` : undefined} className="m-0 font-head text-xl leading-tight tracking-normal">
          {title}
        </h2>
        {actions}
      </div>
      {lead ? <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">{lead}</p> : null}
      {children}
    </section>
  );
}
