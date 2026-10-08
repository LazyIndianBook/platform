// .band / .band-night: full-bleed sections. Night bands (header, hero, final call to action, footer) invert the
// tokens, so buttons, links and muted text inside them follow without their own rules. QRule is the exam-paper
// divider that opens a section ("Q.1 ——— What's inside"). Marker is the one highlighter stroke of a view.
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

/** Three words or fewer, one line; `draw` scales the stroke in as it scrolls into view (motion.md, b). */
function Marker({ children, draw = false }: { children: React.ReactNode; draw?: boolean }) {
  return (
    <mark className="marker" data-draw={draw || undefined}>
      {children}
    </mark>
  );
}

export { Band, Marker, NightBand, QRule };
