// .table-wrap > table, Direction A (Components board, 07): an ink rule on top, the head in the mono label voice, a
// hairline under each row, numbers right-aligned in mono tabular figures, an ink rule above a total (globals.css,
// "tables"). The box scrolls sideways by itself on a phone (wide tables get a min-width instead of squashing) and is a
// named, focusable region, so a keyboard can scroll it in every browser (Safari does not focus a scroller: F10).
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
