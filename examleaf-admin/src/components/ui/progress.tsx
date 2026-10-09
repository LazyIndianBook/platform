// Progress, Direction A (Components board, 07: "PROGRESS · words beside the bar always"): a still 8 px bar in the soft
// rule colour with the done share in navy, and the words beside it ("12 of 48 clips"), never the bar alone. It is a
// role="progressbar" with aria-valuenow and the words as its aria-valuetext, so a screen reader hears the same words
// once (the visible copy is hidden from it). `name` labels the bar ("Clips watched"); by default the words do.
import { cn } from "cn";

type ProgressProps = {
  value: number;
  max?: number;
  /** The words beside the bar, e.g. "12 of 48 clips". */
  label: string;
  /** What the bar measures, for screen readers ("Clips watched"); the words when left out. */
  name?: string;
  className?: string;
};

function Progress({ value, max = 100, label, name, className }: ProgressProps) {
  const now = Math.min(Math.max(value, 0), max);
  const share = max > 0 ? (now / max) * 100 : 0;
  return (
    <div className={cn("flex items-center gap-3.5 text-[15px] text-muted-foreground", className)}>
      <span
        role="progressbar"
        aria-label={name ?? label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={now}
        aria-valuetext={label}
        className="block h-2 min-w-16 flex-1 bg-rule-soft"
      >
        <span className="block h-full bg-primary" style={{ width: `${share}%` }} />
      </span>
      <span aria-hidden="true">{label}</span>
    </div>
  );
}

export { Progress };
