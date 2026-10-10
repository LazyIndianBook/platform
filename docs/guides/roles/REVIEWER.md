# Reviewer (REVIEWER)

Role guide. Written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the panel's People → Roles
page (`/people/roles/`) is the running truth. The index is [README.md](README.md).

## Who this is for

For senior editors: reading content and the course, and publishing papers. Nothing an editor writes reaches the site
until you publish it, and you never decide on a draft you wrote or submitted. You work inside your subjects when your
account has a subject scope.

## What you can do

- **Reviews** (`/content/reviews/`): the drafts waiting for you, each with its line diff beside the preview as the site
  draws it. Approve it, ask for changes with a comment (the editor is told and the record is a draft again), or publish it,
  approving it on the way. A publish can be undone for five seconds ("Undo"); later, the solution's editor has "Undo the
  last publish", which puts the text before it back live and the published text back into the draft.
- **Papers:** publish or unpublish a paper, or make it its book's open sample (the sample moves from the book's other
  paper). You read books, papers, questions, solutions and the legal deposits.
- **Reported mistakes** (`/content/reports/`): triage them as the editors do (confirm, reject with a reason, fixed online,
  fixed in a printing, tell the reporter).
- **Imports** (`/content/imports/`): after the books repository changed, run a subject's dry run (new, changed, the same,
  not matched, no longer in the books) and then its apply, which refuses if the repository moved since or after 24 hours.
  You confirm it's you first.
- **Course** (`/course/`): read the outline and the quiz bank; approve a revision, send it back with what to change,
  publish it now or at a time within a year (it needs a ready clip), or put it back to draft (students keep their
  progress). Never your own submission.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Write or edit a question, a solution, a book or a course row | a CONTENT_EDITOR |
| Decide on a draft you edited or submitted (`own_edit`, owners included) | another REVIEWER of the subject |
| Record a legal deposit | a CONTENT_EDITOR |
| See customers, orders or money; change the shop | SUPPORT, SALES, FINANCE |
| Run a bulk action or an export | none in your role (limits are 0) |

## Your limits

None to speak of: your role has no refund, payment, discount, export or bulk limit, because it holds none of those
permissions. My account → "Your limits" shows it.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Content home | `/content/` | reviews for you, mistakes to triage, the last import |
| Reviews | `/content/reviews/`, `/content/reviews/<id>/` | the diff, the preview, approve, ask for changes, publish |
| Papers | `/content/papers/`, `/content/papers/<id>/` | publish or unpublish a paper |
| Reported mistakes | `/content/reports/` | triage |
| Imports | `/content/imports/` | a dry run, then its apply |
| Course | `/course/revisions/<id>/` | a revision's review and publish |
| Inbox | `/inbox/` | the review and mistake items, by subject |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with the email and password an owner
   gave you ([README.md](README.md) "Before a person's first day"); if the console says "Set up two-step sign-in first",
   follow its link, scan the QR code with an authenticator app and keep the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role and where you are signed in. Ask an owner which subjects are yours.
4. Open the Inbox: the reviews and revisions waiting, the mistakes to triage.
5. Open one review with the editor who wrote it: read the diff, the preview, and the History before you publish.

## In RUNBOOK.md

"Content" ("Importing papers after the books changed", "A reader reported a wrong solution", "Undoing a publish");
"The revision course" ("Uploading and publishing a revision"); "The inbox".
