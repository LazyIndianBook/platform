// The paper's masthead (was the navy QR card), as "A Solutions" draws it: the mono eyebrow (code, paper, tier,
// class), the title in serif on one line, the facts in a ruled row (Full marks · Pass marks · Time) and the red
// EXAMLEAF · OFFICIAL SOLUTIONS stamp, which the wall leaves out (stamp={false}). The subject, tier and code props
// are kept for the callers; the artboard draws no chip row, the eyebrow carries their words. The stamp is decorative
// (aria-hidden); the facts are a real <dl>.
import { cn } from "cn";

import type { SubjectKey, TierCode } from "@/lib/site";

type QrCardProps = {
  subject: SubjectKey;
  subjectName: string;
  tier: TierCode;
  code: string;
  eyebrow: string;
  title: string;
  facts: { label: string; value: string | number }[];
  headingLevel?: 1 | "p";
  compact?: boolean;
  /** The red stamp at the right (default); the wall shows the masthead without it. */
  stamp?: boolean;
};

function QrCard({ eyebrow, title, facts, headingLevel = 1, compact, stamp = true }: QrCardProps) {
  const Title = headingLevel === 1 ? "h1" : "p";
  return (
    <div className="qr-card relative flex flex-col gap-5">
      <p className={cn("m-0 label-mono uppercase", stamp && "pr-[140px] max-nav:pr-[88px]")}>{eyebrow}</p>
      <Title
        className={cn(
          "m-0 font-display leading-none font-semibold tracking-[-0.02em] text-balance text-foreground",
          stamp && "pr-[140px] max-nav:pr-[88px]",
          compact ? "text-[32px]" : "text-[clamp(36px,5vw,60px)]",
        )}
      >
        {title}
      </Title>
      <dl className="m-0 flex flex-wrap self-start border-t-[1.5px] border-b border-t-foreground border-b-border">
        {facts.map((fact, index) => (
          <div
            key={fact.label}
            className={cn("flex flex-col gap-1 py-3.5 pr-7", index > 0 && "border-l border-border pl-7")}
          >
            <dt className="text-[13px] leading-snug text-muted-foreground">{fact.label}</dt>
            <dd className="m-0 font-mono text-[26px] leading-none font-semibold text-foreground max-nav:text-[20px]">
              {fact.value}
            </dd>
          </div>
        ))}
      </dl>
      {stamp ? (
        <span
          aria-hidden="true"
          className={cn(
            "seal absolute top-2 right-0 max-nav:size-[76px] max-nav:text-[9px]",
            compact && "size-24 text-[10px]",
          )}
        >
          ExamLeaf
          <br />
          Official
          <br />
          solutions
        </span>
      ) : null}
    </div>
  );
}

export { QrCard };
