// details.accordion, Direction A (Components board, 06): native <details> (works without script; one name opens one
// at a time); hairline rows, the question in the serif, "+" closed and "−" open in red mono (globals.css draws the
// sign in an aria-hidden span, so the question is all a screen reader hears). Nothing turns or slides.
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
        <span aria-hidden="true" data-sign="" />
      </summary>
      <div>{children}</div>
    </details>
  );
}

export { Accordion };
