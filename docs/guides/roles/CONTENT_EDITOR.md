# Content editor (CONTENT_EDITOR)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds CONTENT_EDITOR: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| ₹0 | ₹0 | 0% | 0 rows | 200 rows | 30 minutes idle, 8 hours in all | an authenticator app or a passkey |

## Who this is for

For authors and editors: books, papers, questions, solutions, legal pages and the course's content. You write and correct
the text and the course; a second person, a REVIEWER, publishes it. You work inside your subjects when your account has
a subject scope.

## What you can do

- **Content** (`/content/`): the home shows what waits (reported mistakes, reviews, your drafts, books missing their legal
  deposits, the last import). Add a book and keep its ISBN, format, edition and publication day. A paper's title, its time,
  and its questions and solutions as a tree. The editor of a question or a solution shows the Markdown and LaTeX on the
  left and the text as the site draws it on the right; every formula is checked before a save. A save writes the draft,
  never the live text; "Submit for review" sends it to a reviewer of the subject. You see every version in the history
  and may bring one back as a draft. The QR code of a print run (type its label).
- **Reported mistakes and errata** (`/content/reports/`, `/content/errata/`): triage what readers report (confirm, reject
  with a reason, fixed online, fixed in a printing with the print run's label, tell the reporter once).
- **Legal deposits** (`/content/legal-deposits/`): record each library's copy, the day it went and the proof.
- **Course** (`/course/`): the outline of your subjects: move a row first, last, before or after another (drag it, or
  "Move to…"), edit, delete (it goes to a 30-day bin and may be restored) and write the must-do note; a revision's title
  and length, and "Submit for review"; "Retry" on a clip that failed; the quiz bank, with an item's text, key and
  metadata changed, many at once with a dry run first (up to 200 rows), and "Needs checking" for an item that looks wrong.
- **Catalogue** (`/catalogue/`): a product page's words, shelves, attributes, pictures, search words and a bundle's books,
  new products (made at their MRP and off sale), the shelf tree, collections and product types. Not prices, tax or
  stock. **Policy versions** (`/privacy/policies/`): publish a new version of a legal page.
- **Support** (`/support/`): you read the content-error tickets and write notes on them, and never answer them.
- **In the Django admin, which your role may open:** upload a clip's video under Revision course. The text of questions
  and solutions is read-only there: it changes through the panel's review.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Publish or unpublish a paper, approve a draft, or publish a revision | a REVIEWER of the subject (never on your own draft, owners included) |
| Import papers from the books repository | a REVIEWER, ADMIN or an owner |
| Change a price, tax or stock; make coupons | SALES, FINANCE, MARKETING |
| Answer a support ticket | SUPPORT |
| See customers, orders or money | SUPPORT, SALES, FINANCE |
| Give access to the course, or make or void book codes | SUPPORT; SALES; ADMIN |

## Your limits

| What | Up to |
|---|---|
| Rows in a bulk action (the quiz bank's metadata) | 200 |
| Refunds, offline payments, discounts, exports | none |

My account → "Your limits" shows them.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Content home | `/content/` | what waits for you |
| Books, papers | `/content/books/`, `/content/papers/` | a book's facts; the questions and solutions, the editor |
| Reviews | `/content/reviews/` | the state of the drafts you submitted |
| Reported mistakes, errata | `/content/reports/`, `/content/errata/` | triage; what was fixed in which printing |
| Legal deposits | `/content/legal-deposits/` | the four libraries' copies |
| Course | `/course/`, `/course/revisions/<id>/`, `/course/clips/<id>/`, `/course/items/`, `/course/bin/` | the outline, revisions, clips, the quiz bank, the bin |
| Catalogue | `/catalogue/products/`, `/catalogue/categories/`, `/catalogue/collections/` | product pages and shelves |
| Policy versions | `/privacy/policies/` | the legal pages |
| Inbox | `/inbox/` | what waits, by subject |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with your email address and the
   password you chose when you accepted the invitation ([README.md](README.md) "Before a person's first day"); if the
   console says "Set up two-step sign-in first", follow its link, scan the QR code with an authenticator app and keep
   the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role, "Your limits" and where you are signed in. Ask an owner which subjects are yours (they see
   your scopes in People → your page → Access; you do not have that page).
4. Open the Inbox and the Content home: the reported mistakes of your subjects, the reviews sent back to you.
5. Open a solution in the editor, change a word, save the draft and discard it; look at its History.

## In RUNBOOK.md

"Content" (all of it: importing papers, a wrong solution reported, undoing a publish, QR codes for print, legal
deposits); "The revision course" (uploading and publishing a revision, a clip that failed); "The shop" ("Categories,
collections, attributes"); "Data requests and privacy" ("Legal holds, policy versions …"); "The inbox".

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the limits above are placeholders until the owner sets them.
- [The content app](../../../examleaf-web/content/README.md): drafts, review, errata and imports.
- [The course app](../../../examleaf-web/learn/README.md): the outline, revisions and the quiz bank.
