// details.accordion: native <details> (works without script; one name opens one at a time); the chevron turns as a
// state, the turn itself animates only in the motion wrapper (globals.css).
import { ChevronDown } from "lucide-react";

function Accordion({
  summary,
  name,
  open,
  children,
}: {
  summary: React.ReactNode;
  name?: string;
  open?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="accordion" name={name} open={open}>
      <summary>
        <span>{summary}</span>
        <ChevronDown aria-hidden="true" className="size-[22px] shrink-0" />
      </summary>
      <div>{children}</div>
    </details>
  );
}

export { Accordion };
