// .table-wrap > table: a scroll box on phones (wide tables get a min-width instead of squashing), sticky header,
// numbers right-aligned in tabular figures, a 2 px rule above the total (globals.css, "tables"). The box is a named,
// focusable region, so a keyboard can scroll it in every browser (Safari does not focus a scroller by itself: F10).
import { cn } from "cn";
import * as React from "react";

function Table({ className, caption, children, ...props }: React.ComponentProps<"table"> & { caption: string }) {
  return (
    <div data-slot="table-wrap" className="table-wrap" role="region" aria-label={caption} tabIndex={0}>
      <table className={className} {...props}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

function TableHead({ className, numeric, ...props }: React.ComponentProps<"th"> & { numeric?: boolean }) {
  return <th scope="col" className={cn(numeric && "num", className)} {...props} />;
}

function TableCell({ className, numeric, ...props }: React.ComponentProps<"td"> & { numeric?: boolean }) {
  return <td className={cn(numeric && "num", className)} {...props} />;
}

export { Table, TableCell, TableHead };
