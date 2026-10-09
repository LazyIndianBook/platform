// The frame of the pages before the console opens (sign in, the second step, no access, set up two-step sign-in):
// the wordmark, then one 480 px sheet against the answer booklet's red double rule, on paper. Under 480 px the sheet
// is the page, the rule at its left edge.
import { Brand } from "@/components/shell/brand";
import { copy } from "@/lib/copy";

export function AuthFrame({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a className="skip-link" href="#main">
        {copy.app.skip}
      </a>
      <header className="flex justify-center px-4 pt-10 pb-6 max-[479px]:justify-start max-[479px]:pt-5 max-[479px]:pb-3">
        <Brand />
      </header>
      <main id="main" tabIndex={-1} className="flex justify-center px-4 pb-16 max-[479px]:px-0">
        <div className="flex w-full max-w-[480px] flex-col gap-4 border-l-[3px] border-double border-red-ink bg-card px-7 py-8 max-[479px]:border-y-0 max-[479px]:px-4 max-[479px]:py-6 [&>*]:m-0">
          {children}
        </div>
      </main>
    </>
  );
}

export function AuthTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="text-[clamp(26px,4vw,32px)] leading-tight tracking-[-0.01em]">{children}</h1>;
}

export function Lead({ children }: { children: React.ReactNode }) {
  return <p className="text-[15px] leading-relaxed text-ink/85">{children}</p>;
}
