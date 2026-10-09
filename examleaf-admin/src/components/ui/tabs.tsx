// .tabs, Direction A (Components board, 06): radio-based, so they filter with CSS alone (:has()) and the arrow keys
// move between them as in any radio group; the row scrolls on a phone, never wraps, over a hairline. Public Sans 600:
// the checked tab in ink over a 2 px red-ink underline, the others muted (ink on hover). Server component: no script.
// min-w-0: a fieldset is as wide as its content by default, which would push the page sideways instead of letting the
// row scroll (accessibility review F2).
import { cn } from "cn";

type TabsProps = {
  name: string;
  legend: string;
  options: { value: string; label: string }[];
  value?: string;
  className?: string;
};

function Tabs({ name, legend, options, value, className }: TabsProps) {
  return (
    <fieldset className={cn("m-0 min-w-0 border-0 p-0", className)}>
      <legend className="sr-only">{legend}</legend>
      <div className="flex overflow-x-auto border-b border-border">
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "relative inline-flex min-h-12 cursor-pointer items-center px-4 font-body text-base leading-tight font-semibold whitespace-nowrap text-muted-foreground hover:text-foreground",
              "has-checked:text-foreground has-checked:shadow-[inset_0_-2px_0_var(--red-ink)]",
              "has-focus-visible:outline-2 has-focus-visible:-outline-offset-2 has-focus-visible:outline-ring",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              defaultChecked={option.value === (value ?? options[0]?.value)}
              className="absolute size-px opacity-0"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export { Tabs };
