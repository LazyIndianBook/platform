// Small display helpers that server pages and client components share (a "use client" module's functions cannot be
// called from a server component, so they live here).
import type { DataRequest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

/** A data request's requester as the API masks them: the email address, else the mobile number. */
export function requesterLabel(request: Pick<DataRequest, "requester">): string {
  return request.requester.masked_email ?? request.requester.masked_phone ?? copy.common.unknown;
}
