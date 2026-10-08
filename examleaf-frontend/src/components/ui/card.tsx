// .card: white, radius 12, hairline, one soft shadow; header 20 20 0, body 20 (dense 16), footer with a top rule.
// CardLink is .card-interactive: the whole card is the link, lifting 2 px on hover (motion wrapper), ring on focus.
import { cn } from "cn";
import Link from "next/link";
import * as React from "react";

function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex min-w-0 flex-col rounded-lg border border-border bg-card text-card-foreground shadow-card",
        className,
      )}
      {...props}
    />
  );
}

function CardLink({ className, ...props }: React.ComponentProps<typeof Link>) {
  return (
    <Link
      data-slot="card"
      className={cn(
        "flex min-w-0 flex-col rounded-lg border border-border bg-card text-card-foreground no-underline shadow-card hover:no-underline",
        "motion-safe:transition-[translate] motion-safe:duration-150 motion-safe:ease-enter motion-safe:hover:-translate-y-0.5",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-header" className={cn("flex flex-col gap-1 px-5 pt-5", className)} {...props} />;
}

function CardTitle({ className, as: Tag = "h2", ...props }: React.ComponentProps<"h2"> & { as?: "h1" | "h2" | "h3" }) {
  return <Tag data-slot="card-title" className={cn("m-0 text-card-title leading-tight", className)} {...props} />;
}

function CardDescription({ className, ...props }: React.ComponentProps<"p">) {
  return <p data-slot="card-description" className={cn("m-0 text-base text-muted-foreground", className)} {...props} />;
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("flex flex-col gap-3 p-5 [&>*]:m-0", className)} {...props} />;
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex flex-wrap items-center gap-3 border-t border-border px-5 py-4", className)}
      {...props}
    />
  );
}

export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardLink, CardTitle };
