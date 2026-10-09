// /catalogue/, /marketing/, /content/, /course/, /partners/, /support/: the modules planned for the next
// phase, drawn in the sidebar for whoever holds their permissions, each with one honest page that says so and where
// the work is done today (the Django admin; Support's messages by email). No sample data. Any other address, or a
// module the manifest does not open, is a 404.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { staffPage } from "@/lib/api/page";
import { copy } from "@/lib/copy";
import { MODULES, soonModule } from "@/lib/modules";

type Params = { params: Promise<{ segment: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { segment } = await params;
  const planned = MODULES.find((entry) => entry.soon && entry.href === `/${segment}/`);
  return { title: planned ? copy.nav.modules[planned.key] : copy.errors.notFoundTitle };
}

export default async function SoonPage({ params }: Params) {
  const { segment } = await params;
  const { manifest } = await staffPage(`/${encodeURIComponent(segment)}/`);
  const planned = soonModule(segment, manifest);
  if (!planned) notFound();
  const name = copy.nav.modules[planned.key];
  return (
    <>
      <PageHeader title={name} />
      <EmptyState
        art="sheet"
        eyebrow={copy.soon.eyebrow}
        title={copy.soon.title(name)}
        action={
          // Django's admin (Caddy, and the proxy in development, send /admin/ there): a page load, not a route here
          // eslint-disable-next-line @next/next/no-html-link-for-pages
          <a href="/admin/" className={buttonVariants({ variant: "secondary" })}>
            {copy.soon.admin}
          </a>
        }
      >
        <p>{copy.soon.today[planned.key] ?? copy.soon.text}</p>
      </EmptyState>
    </>
  );
}
