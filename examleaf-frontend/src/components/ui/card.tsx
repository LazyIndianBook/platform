// .card, Direction A: a white sheet on paper, hairline border, radius 4, no soft shadow. CardLink: the whole card is
// the link; hover turns the border to ink (no lift: the reading surfaces stay still). API unchanged.
import { cn } from "cn";
import Link from "next/link";
import * as React from "react";

function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn("flex min-w-0 flex-col rounded-lg border border-border bg-card text-card-foreground", className)}
      {...props}
    />
  );
}

function CardLink({ className, ...props }: React.ComponentProps<typeof Link>) {
  return (
    <Link
      data-slot="card"
      className={cn(
        "flex min-w-0 flex-col rounded-lg border border-border bg-card text-card-foreground no-underline hover:border-foreground hover:text-card-foreground hover:no-underline",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-header" className={cn("flex flex-col gap-1 px-6 pt-6", className)} {...props} />;
}

function CardTitle({ className, as: Tag = "h2", ...props }: React.ComponentProps<"h2"> & { as?: "h1" | "h2" | "h3" }) {
  return <Tag data-slot="card-title" className={cn("m-0 text-card-title leading-tight", className)} {...props} />;
}

function CardDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p data-slot="card-description" className={cn("m-0 text-[15px] text-muted-foreground", className)} {...props} />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("flex flex-col gap-3 p-6 [&>*]:m-0", className)} {...props} />;
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex flex-wrap items-center gap-3 border-t border-border px-6 py-4", className)}
      {...props}
    />
  );
}

export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardLink, CardTitle };
