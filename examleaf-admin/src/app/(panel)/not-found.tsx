// A record or a module the console does not have (notFound() in a panel page): inside the frame.
import type { Metadata } from "next";

import { NotFoundView } from "@/components/shell/not-found-view";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.errors.notFoundTitle };

export default function PanelNotFound() {
  return <NotFoundView />;
}
