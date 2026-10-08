// motion.md d, for the App Router's client-side navigations: a shared element that morphs from one page into the next
// (a Home or 404 tile into its book's cover, a product card's cover into the product page's). Only the named pair
// animates (default none), so a form's answer, a refresh or any other navigation changes the page at once; browsers
// without view transitions navigate as usual, and reduced motion stills it (globals.css). Names must be unique on a page.
import { ViewTransition } from "react";

export function Morph({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <ViewTransition name={name} share="auto" default="none">
      {children}
    </ViewTransition>
  );
}
