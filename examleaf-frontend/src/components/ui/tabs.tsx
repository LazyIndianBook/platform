// .tabs: radio-based, so they filter with CSS alone (:has()); the row scrolls on a phone, never wraps; the checked
// label is primary with a 3 px underline. Server component: no script. min-w-0: a fieldset is as wide as its content
// by default, which would push the page sideways instead of letting the row scroll (accessibility review F2).
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
      <div className="flex gap-1 overflow-x-auto border-b border-border">
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "relative inline-flex min-h-12 cursor-pointer items-center px-4 font-head text-[15px] leading-tight font-bold whitespace-nowrap text-muted-foreground hover:text-foreground",
              "has-checked:text-primary has-checked:shadow-[inset_0_-3px_0_var(--primary)]",
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
