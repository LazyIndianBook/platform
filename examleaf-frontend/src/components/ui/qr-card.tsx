// .qr-card: the header of every paper page (/s/<code>/, the URL in the printed QR code): subject, tier and code
// chips, the eyebrow, the title (the page's H1; a <p> in the Home preview), the marks in gold, the "Scan verified"
// seal. On phones the seal tucks beside the facts.
import { cn } from "cn";
import { ScanLine } from "lucide-react";

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
    <div
      className={cn(
        "qr-card flex flex-wrap items-center gap-x-8 gap-y-5 rounded-lg bg-navy px-8 py-7 text-white shadow-card [--ring:#8fd694]",
        "max-nav:grid max-nav:grid-cols-[1fr_auto] max-nav:items-end max-nav:gap-x-3 max-nav:gap-y-2.5 max-nav:p-5",
      )}
    >
      <div
        className={cn(
          "flex min-w-0 flex-[999_1_420px] flex-col gap-2.5 max-nav:contents [&>*]:m-0 max-nav:[&>*]:col-span-full",
          compact && "basis-[280px]",
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={subject}>{subjectName}</Badge>
          <Badge variant={TIER_VARIANT[tier]}>{TIERS[tier]}</Badge>
          <Badge variant="code">{code}</Badge>
        </div>
        <p className="text-base leading-normal font-semibold text-night-muted">{eyebrow}</p>
        <Title
          className={cn(
            "m-0 font-head leading-[1.15] font-extrabold text-balance text-white",
            compact ? "text-[28px]" : "text-[clamp(28px,3.6vw,40px)]",
          )}
        >
          {title}
        </Title>
        <dl className="m-0 flex flex-wrap gap-x-8 gap-y-2 max-nav:col-span-1!">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt className="text-sm leading-snug text-night-muted">{fact.label}</dt>
              <dd className="m-0 font-head text-[26px] leading-tight font-extrabold text-gold max-nav:text-[22px]">
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <span
        aria-hidden="true"
        className={cn(
          "seal max-nav:col-start-2 max-nav:row-start-4 max-nav:m-0 max-nav:size-[76px] max-nav:text-[10px]",
          compact && "size-[88px]",
        )}
      >
        <ScanLine className="size-6 max-nav:size-5" />
        <span className="max-w-20 text-balance max-nav:max-w-[58px]">ExamLeaf · Official solutions</span>
      </span>
    </div>
  );
}

export { QrCard };
