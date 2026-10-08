// About (Django's about.html): the publisher, what the books are, where the solutions are, how to use a paper.
// Direction A (ExamLeaf A - Public.dc.html, "About"): a Sheet with "§" in the margin, the copy in the reading serif,
// and the facts as a ruled list beside it.
import Link from "next/link";

import { Sheet } from "@/components/ui/band";
import { getConfig } from "@/lib/api/config";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "About",
  path: "/about/",
  description:
    "About ExamLeaf LLP, publisher of the ExamLeaf Sample Papers books for the Assam Board (ASSEB) Class 12 examination.",
});

const FACTS = [
  ["Publisher", "ExamLeaf LLP, published by Bhaben Bhuyan"],
  ["Books", "Physics, Chemistry, Mathematics, Biology · ASSEB Class 12"],
  ["In each book", "30 papers: 10 Easy, 10 Medium, 10 Hard"],
] as const;

export default async function AboutPage() {
  const requireLogin = (await getConfig())?.solutions_require_login ?? true;
  return (
    <Sheet
      margin="§"
      className="max-nav:[&>.sheet-margin]:hidden"
      bodyClassName="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-16 max-[1100px]:grid-cols-1 max-[1100px]:gap-10 max-nav:pt-6"
    >
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "About", path: "/about/" },
        ])}
      />
      <article className="flex max-w-[40em] min-w-0 flex-col gap-[22px] max-nav:gap-4">
        <h1 className="m-0 text-[clamp(38px,5vw,64px)] leading-none tracking-[-0.025em]">About ExamLeaf</h1>
        <p className="m-0 font-head text-[clamp(21px,2.4vw,26px)] leading-[1.45] text-ink/85 italic">
          The book is the exam hall; this site is the answer key.
        </p>
        <div className="prose text-[19px] max-nav:text-lg">
          <p>
            The ExamLeaf books are published by <strong>ExamLeaf LLP</strong>. Publisher: <strong>Bhaben Bhuyan</strong>
            . The registered address, the GSTIN and the ways to reach us are on the{" "}
            <Link href="/contact/">Contact</Link> page.
          </p>
          <p>
            The <strong>ExamLeaf Sample Papers</strong> books for the Higher Secondary Final Examination of the Assam
            State School Education Board (ASSEB), Class 12, cover Physics, Chemistry, Mathematics and Biology. Each book
            holds 30 complete papers in the Board&apos;s pattern: 10 Easy papers to build the basics, 10 Medium papers
            at the level of the real examination, and 10 Hard papers for those aiming at the top.
          </p>
          <h2>Where are the solutions?</h2>
          <p>
            The solutions are not printed in the book. Each paper carries a QR code that opens its solutions on this
            website: the answer to every question, with the steps an examiner gives marks for. They are free
            {requireLogin ? "; you only need to register once, with your email address" : ""}.
          </p>
          <h2>How to use a paper</h2>
          <ol>
            <li>Sit the paper as an examination: three hours, no book open, answers written out in full.</li>
            <li>Scan the QR code on the paper, or open the paper from its book page here.</li>
            <li>Mark your answers step by step against the solutions.</li>
            <li>
              Save your score in <Link href="/account/record/">My record</Link> to follow your progress.
            </li>
          </ol>
          <p className="text-muted-foreground">
            The papers are practice papers prepared by ExamLeaf. They are not question papers issued by ASSEB, and ASSEB
            has no connection with this publication.
          </p>
        </div>
      </article>
      <aside aria-label="ExamLeaf in short" className="border-t-[1.5px] border-foreground">
        <dl className="m-0">
          {FACTS.map(([term, value]) => (
            <div key={term} className="flex flex-col gap-1 border-b border-border py-4">
              <dt className="label-mono text-xs uppercase">{term}</dt>
              <dd className="m-0 text-[17px]">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="m-0 flex flex-wrap gap-x-4 font-bold">
          <Link href="/contact/" className="inline-flex min-h-11 items-center">
            Contact us
          </Link>
          <Link href="/shop/" className="inline-flex min-h-11 items-center">
            Buy the books
          </Link>
        </p>
      </aside>
    </Sheet>
  );
}
