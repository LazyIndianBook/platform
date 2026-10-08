"use client";

// Links into the revision course's web pages, for the pages that list chapters (/revision/, /account/learning/): drawn
// only while config/ has web_course on, so with the flag off (or the config unread) no link leads to a 404.
import Link from "next/link";

import { useConfig } from "@/components/providers/config-provider";
import { subjectOf } from "@/lib/site";

type LinkProps = { children?: React.ReactNode; className?: string };

/** A chapter's page: `subject` is the API's subject code (PHY …), `chapter` the chapter's number. */
export function ChapterLink({
  subject,
  chapter,
  children = "Open the chapter",
  className,
}: LinkProps & { subject: string; chapter: number }) {
  const config = useConfig();
  const key = subjectOf(subject)?.key;
  if (!config?.web_course || !key) return null;
  return (
    <Link href={`/revision/${key}/${chapter}/`} className={className}>
      {children}
    </Link>
  );
}

export function ReviseAgainLink({ children = "Revise again today", className }: LinkProps) {
  const config = useConfig();
  if (!config?.web_course) return null;
  return (
    <Link href="/account/learning/revise-again/" className={className}>
      {children}
    </Link>
  );
}
