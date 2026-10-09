// /support/replies/: the saved replies (GET support/saved-replies/), in English, Assamese and Bengali, with the
// variables each fills in; adding, changing and deleting them (the bin, GET ?bin=true, for 30 days) for whoever may.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { SavedReplies } from "@/components/modules/support/replies";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listSavedReplies } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.support.replies };

export default async function SavedRepliesPage() {
  const { manifest, transport, path } = await staffPage("/support/replies/");
  if (!has(manifest, P.repliesView)) notFound();
  const [replies, bin] = await Promise.all([
    attempt(listSavedReplies({ page_size: 200 }, transport), path),
    has(manifest, P.repliesDelete) ? attempt(listSavedReplies({ bin: true, page_size: 200 }, transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.support.replies}
        lead={copy.support.repliesLead}
        back={{ href: "/support/", label: copy.support.title }}
      />
      {replies instanceof ApiError ? (
        <Problem error={replies} />
      ) : (
        <SavedReplies replies={replies.results} bin={bin instanceof ApiError || bin === null ? null : bin.results} />
      )}
    </>
  );
}
