// Under 900 px the marks column is gone, so a hero's figures ([30] papers, [70] marks, [3h]) sit in one row under its
// text (Phone home, Phone book). Decorative like the desktop column (aria-hidden): the page says the same in words.
export function PhoneFigures({ items }: { items: { value: string | number; label: string }[] }) {
  return (
    <div aria-hidden="true" className="flex gap-[18px] nav:hidden">
      {items.map((item) => (
        <span key={item.label} className="numeral text-[22px]">
          [{item.value}]
          <span className="mt-1 block font-body text-xs leading-snug font-normal text-muted-foreground">
            {item.label}
          </span>
        </span>
      ))}
    </div>
  );
}
