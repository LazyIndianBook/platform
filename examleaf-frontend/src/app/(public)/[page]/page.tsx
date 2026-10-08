// The legal and policy pages (/privacy/ /terms/ /refunds/ /shipping/ /contact/) from GET /api/v1/pages/<slug>/: the
// website's HTML of the Markdown (raw HTML is off on the server; a [placeholder] still to fill in comes marked
// <mark class="placeholder">), the version and the date of the last change.
import { Mail } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Card, CardContent } from "@/components/ui/card";
import { getLegalPage, type LegalPage } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { pageMetadata } from "@/lib/seo/metadata";

const SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"] as const;
type Slug = (typeof SLUGS)[number];

export const dynamicParams = false;
export function generateStaticParams() {
  return SLUGS.map((page) => ({ page }));
}

type Props = { params: Promise<{ page: string }> };

async function load(slug: string): Promise<LegalPage | null | "unavailable"> {
  try {
    return await getLegalPage(slug as Slug);
  } catch (error) {
    return error instanceof ApiError && error.status === 404 ? null : "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { page: slug } = await params;
  const page = await load(slug);
  const title = page && page !== "unavailable" ? page.title : "ExamLeaf";
  return pageMetadata({
    title,
    path: `/${slug}/`,
    description: `ExamLeaf LLP, publisher of the ExamLeaf books and website: ${title}.`,
  });
}

const date = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Kolkata",
});

export default async function LegalPageView({ params }: Props) {
  const { page: slug } = await params;
  const page = await load(slug);
  if (page === null) notFound();
  if (page === "unavailable") return <Unavailable what="This page" retry={`/${slug}/`} />;
  const support = slug === "contact" ? (await getConfig())?.support : null;

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-4">
        <article className="prose">
          <h1>{page.title}</h1>
          <div dangerouslySetInnerHTML={{ __html: page.html }} />
          <p className="text-muted-foreground">
            Version {page.version} · last changed {date.format(new Date(page.updated))}
          </p>
        </article>
        {support?.email ? (
          <Card className="max-w-[38rem]">
            <CardContent>
              <h2 className="m-0 text-card-title">Write to us</h2>
              <p>
                <a href={`mailto:${support.email}`} className="inline-flex min-h-11 items-center gap-2 font-semibold">
                  <Mail aria-hidden="true" className="size-5" />
                  {support.email}
                </a>
              </p>
              <p className="text-small text-muted-foreground">We reply by email.</p>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </section>
  );
}
