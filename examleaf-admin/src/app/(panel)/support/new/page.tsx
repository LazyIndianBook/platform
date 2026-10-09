// /support/new/: log a complaint that came by phone, WhatsApp, the National Consumer Helpline (with its docket) or an
// email (POST support/tickets/), for whoever handles tickets; the new ticket opens once it is logged.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LogTicketForm } from "@/components/modules/support/log-form";
import { PageHeader } from "@/components/shell/page-header";
import { requestTime, staffPage } from "@/lib/api/page";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.support.newTitle };

export default async function NewTicketPage() {
  const { manifest } = await staffPage("/support/new/");
  if (!has(manifest, P.ticketsHandle)) notFound();
  return (
    <>
      <PageHeader
        title={copy.support.newTitle}
        lead={copy.support.newLead}
        back={{ href: "/support/", label: copy.support.title }}
      />
      <LogTicketForm now={requestTime()} />
    </>
  );
}
