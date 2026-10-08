// The log-in and register pages' frame (Login and Register artboards): a card on the paper's alternate colour,
// with an optional aside ("Why log in", "What we keep") that drops under it on a phone.
import { cn } from "cn";

export function AuthSection({
  children,
  aside,
  wide = false,
}: {
  children: React.ReactNode;
  aside?: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <section className="flex-1 bg-secondary pt-16 pb-(--section) max-nav:pt-8">
      <div className="container-site flex flex-wrap items-start justify-center gap-x-16 gap-y-10">
        <div
          className={cn(
            "flex min-w-0 flex-col gap-3.5 rounded-lg border border-border bg-card p-7 max-nav:p-5 [&>*]:m-0",
            wide ? "flex-[999_1_600px] gap-4 p-8" : "flex-[0_1_460px]",
          )}
        >
          {children}
        </div>
        {aside}
      </div>
    </section>
  );
}

export function AuthTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="text-h1-card">{children}</h1>;
}
