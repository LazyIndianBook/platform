// A ticket's conversation, oldest first (no hooks: drawn by the server): what the customer wrote, the replies (staff's
// and the site's own acknowledgement, each with how it went) and the internal notes (shaded, with the colleagues they
// named), the files kept (opened through the API, which logs each) and those not kept with why. An email from another
// address than the requester's says so before anyone answers it.
import { cn } from "cn";
import { Paperclip } from "lucide-react";

import { type Agent, type TicketMessage, type TicketRecord, ticketAttachmentHref } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatBytes, formatDateTime } from "@/lib/format";

import { agentName } from "./shared";

function author(message: TicketMessage, ticket: TicketRecord): string {
  if (message.direction === "in")
    return message.other_sender ? copy.support.fromSomeone : ticket.requester.name || copy.support.fromCustomer;
  if (message.automatic) return copy.support.fromSite;
  return message.author_name || copy.support.fromSite;
}

export function Conversation({ ticket, agents, me }: { ticket: TicketRecord; agents: Agent[] | null; me: number }) {
  if (!ticket.messages.length)
    return <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noMessages}</p>;
  return (
    <ol className="m-0 flex list-none flex-col gap-4 p-0">
      {ticket.messages.map((message) => (
        <li
          key={message.id}
          data-direction={message.direction}
          className={cn(
            "flex flex-col gap-2 border-l-[3px] py-1 pl-4",
            message.direction === "in" && "border-foreground",
            message.direction === "out" && "border-primary",
            message.direction === "note" && "border-warning-line bg-warning-bg py-3 pr-3",
          )}
        >
          <p className="m-0 text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">{author(message, ticket)}</span>
            {" · "}
            {labelOf(copy.support.messageKinds, message.direction)}
            {message.direction !== "note"
              ? ` ${copy.support.via(labelOf(copy.support.channels, message.channel))}`
              : ""}
            {message.automatic ? ` (${copy.support.automatic})` : ""}
            {" · "}
            <time dateTime={message.sent_at}>{formatDateTime(message.sent_at)}</time>
          </p>
          {message.other_sender ? (
            <p className="m-0 text-sm font-semibold text-destructive">{copy.support.otherSender}</p>
          ) : null}
          <div className="text-[15px] leading-relaxed break-words whitespace-pre-wrap">{message.body}</div>
          {message.attachments.length ? (
            <ul aria-label={copy.support.files} className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-sm">
              {message.attachments.map((file) => (
                <li key={file.id}>
                  <a
                    href={ticketAttachmentHref(ticket.number, file.id)}
                    className="inline-flex min-h-6 items-center gap-1.5"
                  >
                    <Paperclip aria-hidden="true" className="size-4" />
                    {copy.support.fileSize(file.name, formatBytes(file.size))}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
          {message.dropped.length ? (
            <p className="m-0 text-sm text-muted-foreground">
              {copy.support.dropped}: {message.dropped.join("; ")}
            </p>
          ) : null}
          {message.mentions.length ? (
            <p className="m-0 text-sm text-muted-foreground">
              {copy.support.mentioned(message.mentions.map((id) => agentName(agents, id, me)).join(", "))}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
