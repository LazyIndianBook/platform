// /<slug>/versions/: every version of a legal page (GET /api/v1/pages/<slug>/versions/), newest first: its number, the
// day it is in force from (or comes into force on), and what it changed. The text of each is kept on the server; the
// page links back to the version in force. Direction A ("Legal"): the Sheet, a ruled list in the reading voice.
import "../legal.css";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Sheet } from "@/components/ui/band";
import { getLegalPage } from "@/lib/api/catalogue";
import { ApiError, unwrap } from "@/lib/api/errors";
import { publicFetch, serverApi } from "@/lib/api/server";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

const SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"] as const;
type Slug = (typeof SLUGS)[number];

export const dynamicParams = false;
export function generateStaticParams() {
  return SLUGS.map((page) => ({ page }));
}

type Props = { params: Promise<{ page: string }> };

async function load(slug: Slug) {
  try {
    const [page, versions] = await Promise.all([
      getLegalPage(slug),
      unwrap(serverApi.GET("/api/v1/pages/{slug}/versions/", { params: { path: { slug } }, ...publicFetch("pages") })),
    ]);
    return { page, versions };
  } catch (error) {
    return error instanceof ApiError && error.status === 404 ? null : "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { page: slug } = await params;
  const found = await load(slug as Slug);
  const title = found && found !== "unavailable" ? `${found.page.title}: versions` : "Versions";
  return pageMetadata({ title, path: `/${slug}/versions/`, description: `Every version of ExamLeaf's ${title}.` });
}

export default async function VersionsPage({ params }: Props) {
  const { page: slug } = await params;
  const found = await load(slug as Slug);
  if (found === null) notFound();
  if (found === "unavailable") return <Unavailable what="This page" retry={`/${slug}/versions/`} />;
  const { page, versions } = found;
  return (
    <Sheet className="max-nav:[&>.sheet-margin]:hidden" bodyClassName="legal-body max-nav:pt-6">
      <div className="flex max-w-[44rem] flex-col gap-5 [&>*]:m-0">
        <p className="label-mono uppercase">
          <Link href={`/${slug}/`}>{page.title}</Link>
        </p>
        <h1 className="text-[clamp(38px,5vw,60px)] leading-none">Every version</h1>
        <p className="text-lg leading-relaxed text-ink/85 max-nav:text-[15px]">
          Each change to the {page.title.toLowerCase()} is a new version, numbered, with the day it is in force from.
          What you agreed to is kept with the version you agreed under.
        </p>
        <ol className="m-0 list-none border-t-[1.5px] border-foreground p-0">
          {versions.map((version) => (
            <li key={version.number} className="flex flex-col gap-1 border-b border-border py-4">
              <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <strong className="font-head text-xl">Version {version.number}</strong>
                <span className="text-muted-foreground">
                  {version.upcoming
                    ? `comes into force on ${formatDate(version.effective_from, "long")}`
                    : `in force from ${formatDate(version.effective_from, "long")}`}
                  {version.in_force ? " · in force now" : ""}
                </span>
              </span>
              {version.summary ? <span className="leading-relaxed">{version.summary}</span> : null}
            </li>
          ))}
        </ol>
        <p>
          <Link href={`/${slug}/`} className="inline-flex min-h-11 items-center font-bold">
            Read the version in force
          </Link>
        </p>
      </div>
    </Sheet>
  );
}
