// About (Django's about.html): the publisher, what the books are, where the solutions are, how to use a paper.
import Link from "next/link";

import { getConfig } from "@/lib/api/config";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "About",
  path: "/about/",
  description:
    "About ExamLeaf LLP, publisher of the ExamLeaf Sample Papers books for the Assam Board (ASSEB) Class 12 examination.",
});

export default async function AboutPage() {
  const requireLogin = (await getConfig())?.solutions_require_login ?? true;
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site">
        <JsonLd
          data={breadcrumbJsonLd([
            { name: "Home", path: "/" },
            { name: "About", path: "/about/" },
          ])}
        />
        <article className="prose">
          <h1>About ExamLeaf</h1>
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
        </article>
      </div>
    </section>
  );
}
