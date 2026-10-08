// The paper's masthead (was the navy QR card), Direction A: the mono eyebrow, the title in serif, the facts in a ruled
// row (Full marks · Pass marks · Time) and the red EXAMLEAF · OFFICIAL SOLUTIONS stamp. Same props. The stamp is
// decorative (aria-hidden); the facts are a real <dl>.
import { cn } from "cn";

import { TIERS, type SubjectKey, type TierCode } from "@/lib/site";

import { Badge, TIER_VARIANT } from "./badge";

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
};

function QrCard({ subject, subjectName, tier, code, eyebrow, title, facts, headingLevel = 1, compact }: QrCardProps) {
  const Title = headingLevel === 1 ? "h1" : "p";
  return (
    <div className="qr-card relative flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={subject}>{subjectName}</Badge>
        <Badge variant={TIER_VARIANT[tier]}>{TIERS[tier]}</Badge>
        <Badge variant="code">{code}</Badge>
      </div>
      <p className="m-0 label-mono uppercase">{eyebrow}</p>
      <Title
        className={cn(
          "m-0 max-w-[14ch] pr-[140px] font-head leading-none font-semibold tracking-[-0.02em] text-balance text-foreground max-nav:pr-[88px]",
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
    </div>
  );
}

export { QrCard };
