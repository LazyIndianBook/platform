// /privacy/holds/<id>/: one legal hold (GET privacy/holds/{id}/): what it keeps (an account or a record, by number),
// why, until when, who made it; once released, by whom and why. Releasing it (POST release/, with a reason) is its
// Danger section. Its notes and audit events beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { DangerRow, Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { ReleaseHold } from "@/components/modules/privacy/holds";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getHold } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { heldLabel, holdState, staffLabel } from "@/lib/display";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";
import { targetHref } from "@/lib/targets";

export const metadata: Metadata = { title: copy.legal.holdsTitle };

export default async function HoldPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/privacy/holds/${encodeURIComponent(id)}/`);
  const hold = await attempt(getHold(recordId(id), transport), path, "404");
  const back = { href: "/privacy/holds/", label: copy.legal.holdsTitle };
  if (hold instanceof ApiError)
    return (
      <RecordPage title={copy.legal.holdsTitle} back={back}>
        <Problem error={hold} />
      </RecordPage>
    );
  const me = manifest.user.id;
  const state = holdState(hold);
  const href = hold.user ? `/users/${hold.user}/` : targetHref(hold.target_type, hold.target_id);
  return (
    <RecordPage
      eyebrow={copy.legal.holdsTitle}
      title={copy.legal.holdNumber(hold.id)}
      back={back}
      status={
        <StatusChip tone={state === "active" ? "waiting" : "stopped"}>
          {labelOf(copy.legal.holdStates, state)}
        </StatusChip>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.legalhold", target_id: String(hold.id) },
        note: { type: "accounts.legalhold", id: String(hold.id) },
      })}
      danger={
        hold.active && has(manifest, P.holdsManage) ? (
          <DangerRow title={copy.legal.release} text={copy.legal.releaseText}>
            <ReleaseHold hold={hold} />
          </DangerRow>
        ) : undefined
      }
    >
      <Facts
        items={[
          {
            label: copy.legal.holdKind,
            value: href ? <Link href={href}>{heldLabel(hold)}</Link> : heldLabel(hold),
          },
          { label: copy.legal.holdReason, value: labelOf(copy.legal.holdReasons, hold.reason) },
          ...(hold.note
            ? [{ label: copy.legal.holdNote, value: <span className="whitespace-pre-wrap">{hold.note}</span> }]
            : []),
          { label: copy.legal.holdUntil, value: hold.until ? formatDate(hold.until) : copy.legal.untilReleased },
          {
            label: copy.legal.holdColumns.made,
            value: copy.legal.holdMadeBy(formatDateTime(hold.created), staffLabel(hold.created_by, me)),
          },
          ...(hold.released_at
            ? [
                {
                  label: copy.legal.holdStates.released,
                  value: (
                    <>
                      {copy.legal.holdReleased(formatDateTime(hold.released_at), staffLabel(hold.released_by, me))}
                      {hold.release_reason ? (
                        <span className="block text-sm text-muted-foreground">“{hold.release_reason}”</span>
                      ) : null}
                    </>
                  ),
                },
              ]
            : []),
        ]}
      />
    </RecordPage>
  );
}
