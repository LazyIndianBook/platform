// Bands and the answer booklet. Band / NightBand: full-bleed sections; the night band is now the ink band (footer,
// closing call to action) and inverts the tokens. QRule: the section opener in the margin's voice. Marker: the one
// red-ink emphasis of a view. New in Direction A: Sheet (margin | content behind the red double rule | marks),
// MarkedRow (a row and its mark on one baseline) and Marks (the figures that hang in the marks column).
import { cn } from "cn";
import * as React from "react";

function Band({ night = false, className, ...props }: React.ComponentProps<"section"> & { night?: boolean }) {
  return <section className={cn("relative", night && "band-night", className)} {...props} />;
}

function NightBand(props: React.ComponentProps<"section">) {
  return <Band night {...props} />;
}

function QRule({ number, label }: { number: number; label: string }) {
  return (
    <div className="q-rule">
      <span>Q.{number}</span>
      <span aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

/** `draw` is accepted for the old callers; the red-ink emphasis is never drawn in (nothing moves on load). */
function Marker({ children }: { children: React.ReactNode; draw?: boolean }) {
  return <em className="marker">{children}</em>;
}

type SheetProps = Omit<React.ComponentProps<"section">, "children"> & {
  /** What sits in the left margin: "Q.2", a paper code, "§". Decorative unless it is the only label. */
  margin?: React.ReactNode;
  /** What hangs in the marks column (desktop only; repeat anything essential in the body). */
  marks?: React.ReactNode;
  children: React.ReactNode;
  bodyClassName?: string;
};

function Sheet({ margin, marks, children, className, bodyClassName, ...props }: SheetProps) {
  return (
    <section className={cn("sheet", className)} {...props}>
      <div className="sheet-margin" aria-hidden={typeof margin === "string" ? true : undefined}>
        {margin}
      </div>
      <div className={cn("sheet-body", bodyClassName)}>{children}</div>
      <div className="sheet-marks" aria-hidden="true">
        {marks}
      </div>
    </section>
  );
}

/** A row and its mark on one baseline: `[2]` for marks allotted, `✓ 1` for marks earned. */
function MarkedRow({
  mark,
  allotted = false,
  className,
  children,
  markLabel,
}: {
  mark?: React.ReactNode;
  allotted?: boolean;
  className?: string;
  children: React.ReactNode;
  /** Screen-reader words for the mark, e.g. "1 mark". */
  markLabel?: string;
}) {
  return (
    <div className={cn("marked-row", className)}>
      <div className="min-w-0">{children}</div>
      <span className={cn("mark", allotted && "allotted")}>
        {mark}
        {markLabel ? <span className="sr-only"> ({markLabel})</span> : null}
      </span>
    </div>
  );
}

/** Figures for the marks column: [30] papers in each book. */
function Marks({ items }: { items: { value: string | number; label: string }[] }) {
  return (
    <div className="flex flex-col gap-7">
      {items.map((item) => (
        <div key={item.label}>
          <div className="numeral text-[30px]">[{item.value}]</div>
          <div className="mt-1.5 font-body text-[13px] leading-snug font-normal text-muted-foreground">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
}

export { Band, Marker, MarkedRow, Marks, NightBand, QRule, Sheet };
