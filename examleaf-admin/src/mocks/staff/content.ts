// THE CONTENT MODULE'S PART OF THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next
// dev`; see handler.ts). Fixtures in the API's own shapes (content/staff_api.py) holding every state the module draws
// (a solution live, one with a draft, one in review by a colleague, one sent back, one published from the panel; a
// review in progress, approved, sent back, published and withdrawn; reports reported, confirmed, rejected, fixed
// online and in printing, from a teacher, flagged by the item analysis, on a clip; a book overdue for its legal
// deposits; two imports), and the answers the backend gives: each path's permission, a re-authentication for the
// import, the reviewer who edited a draft never deciding it (403 own_edit), the triage's steps, the drafts kept
// apart from the live text, a rollback, 404 for what is not there. Nothing here is used by the console's own code.
import type { MockJob, MockSchemas } from "./fixtures";

type S = MockSchemas;
type Body = Record<string, unknown>;

export type ContentWorld = {
  books: S["ContentBookDetail"][];
  papers: S["ContentPaperDetail"][];
  questions: S["ContentQuestionDetail"][];
  solutions: S["ContentSolutionDetail"][];
  reviews: S["ContentReviewDetail"][];
  reports: S["ContentReportDetail"][];
  deposits: S["LegalDeposit"][];
  versions: Record<string, S["ContentVersion"][]>;
};

/** What the content routes need of the handler (its helpers and the request's context). */
export type Tools = {
  method: string;
  parts: string[];
  body: Body;
  url: URL;
  me: number;
  can: (perm: string) => boolean;
  world: ContentWorld;
  jobs: MockJob[];
  nextId: () => number;
  json: (status: number, body: unknown) => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  notFound: () => Response;
  refuse: (perm: string) => Response;
  paginate: <T>(rows: T[]) => Response;
  record: (action: string, extra: Partial<S["AuditEvent"]>) => void;
  target: (
    type: string,
    id: number | string,
    label: string,
  ) => Pick<S["AuditEvent"], "target_type" | "target_id" | "target_label">;
};

const PRINTING = /^[A-Za-z0-9][A-Za-z0-9-]{0,39}$/; // content/reports.py: a print run's label
const LIBRARIES = ["national_library", "connemara", "asiatic_society", "delhi_public_library"] as const;
const SOLUTION = [
  "| Step | Marks |",
  "|---|---|",
  "| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |",
  "| $I = \\dfrac{6}{11+1} = 0.5$ A | 1 |",
  "",
  "**Final answer:** 0.5 A",
].join("\n");
const FIXED = SOLUTION.replace("= 0.5$ A", "= 0.50$ A");
const PNG =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg==";

const linesOf = (before: unknown, after: unknown): S["ContentLine"][] => {
  const old = String(before ?? "").split("\n");
  const fresh = String(after ?? "").split("\n");
  return [
    ...old.filter((line) => !fresh.includes(line)).map((text) => ({ op: "delete" as const, text })),
    ...fresh.map((text) => ({ op: old.includes(text) ? ("equal" as const) : ("insert" as const), text })),
  ];
};
const change = (field: string, before: unknown, after: unknown): S["ContentChange"] => ({
  field,
  before,
  after,
  lines: linesOf(before, after),
});

export function createContent(at: (hours: number) => string, me: number, editor: number, reviewer: number) {
  const day = (days: number) => at(days * 24).slice(0, 10);
  const books: S["ContentBookDetail"][] = [
    {
      id: 2101,
      title: "ExamLeaf Physics Sample Papers 2027",
      subject: 1,
      subject_code: "PHY",
      edition: "First edition, 2026",
      slug: "physics-2027",
      cover: "img/physics.png",
      isbn: "9780306406157",
      format: "print",
      published_on: day(-40),
      deposit_due_on: day(-10),
      papers: 2,
      missing_deposits: ["connemara", "asiatic_society", "delhi_public_library"],
    },
    {
      id: 2102,
      title: "ExamLeaf Chemistry Sample Papers 2027",
      subject: 2,
      subject_code: "CHE",
      edition: "First edition, 2026",
      slug: "chemistry-2027",
      cover: "img/chemistry.png",
      isbn: "",
      format: "print",
      published_on: null,
      deposit_due_on: null,
      papers: 1,
      missing_deposits: [...LIBRARIES],
    },
  ];
  const question = (
    row: Partial<S["ContentQuestionDetail"]> &
      Pick<S["ContentQuestionDetail"], "id" | "paper" | "paper_code" | "label">,
  ): S["ContentQuestionDetail"] => ({
    order: 1,
    number: row.label,
    marks_text: "2",
    is_published: true,
    state: "published",
    preview: "",
    solution: null,
    text_md: `A cell of emf 6 V and internal resistance 1 Ω drives a resistor of 11 Ω (${row.label}). Find the current.`,
    table_md: "",
    options_json: [],
    group_label: "2. Answer the following questions `2×5=10`",
    part_label: "",
    is_alternative: false,
    tags: ["Ch 3: Current Electricity"],
    draft: {},
    draft_by: null,
    published_at: null,
    published_by: null,
    review: null,
    ...row,
  });
  const questions = [
    question({
      id: 2301,
      paper: 2201,
      paper_code: "PHY-E01",
      label: "1(a)",
      solution: 2401,
      order: 1,
      marks_text: "1",
    }),
    question({
      id: 2302,
      paper: 2201,
      paper_code: "PHY-E01",
      label: "2(c)",
      solution: 2402,
      order: 2,
      state: "in_review",
      draft: {
        text_md: "A cell of emf $6$ V and internal resistance $1\\,\\Omega$ drives $11\\,\\Omega$. Find the current.",
      },
      draft_by: editor,
    }),
    question({ id: 2303, paper: 2201, paper_code: "PHY-E01", label: "3", solution: 2403, order: 3, marks_text: "3" }),
    question({ id: 2304, paper: 2202, paper_code: "PHY-E02", label: "1(a)", solution: 2404, order: 1 }),
    question({
      id: 2305,
      paper: 2203,
      paper_code: "CHE-E01",
      label: "1(a)",
      solution: 2405,
      order: 1,
      text_md: "Name the gas given off at the anode.",
    }),
    question({
      id: 2306,
      paper: 2201,
      paper_code: "PHY-E01",
      label: "4 OR",
      order: 4,
      is_published: false,
      is_alternative: true,
    }),
  ];
  for (const row of questions) row.preview = row.text_md.slice(0, 140);
  const solution = (
    row: Partial<S["ContentSolutionDetail"]> & Pick<S["ContentSolutionDetail"], "id" | "question">,
  ): S["ContentSolutionDetail"] => {
    const parent = questions.find((each) => each.id === row.question)!;
    return {
      question_label: parent.label,
      paper: parent.paper,
      paper_code: parent.paper_code,
      state: "published",
      preview: SOLUTION.slice(0, 140),
      question_text: parent.text_md,
      marks_text: parent.marks_text,
      body_md: SOLUTION,
      draft: {},
      draft_by: null,
      published_at: null,
      published_by: null,
      review: null,
      ...row,
    };
  };
  const solutions = [
    solution({ id: 2401, question: 2301, body_md: "**Ans.** Equipotential surface. *(1)*" }),
    solution({ id: 2402, question: 2302, state: "in_review", draft: { body_md: FIXED }, draft_by: editor }),
    solution({
      id: 2403,
      question: 2303,
      body_md: "| Step | Marks |\n|---|---|\n| $F = qE$ | 1 |\n| $E = \\dfrac{V}{d}$ | 2 |",
    }),
    solution({ id: 2404, question: 2304, published_at: at(-30), published_by: reviewer }),
    solution({
      id: 2405,
      question: 2305,
      state: "draft",
      body_md: "**Ans.** Oxygen *(1)*",
      draft: { body_md: "**Ans.** Chlorine *(1)*" },
      draft_by: editor,
    }),
  ];
  const paper = (
    row: Partial<S["ContentPaperDetail"]> &
      Pick<S["ContentPaperDetail"], "id" | "code" | "book" | "book_title" | "subject_code">,
  ): S["ContentPaperDetail"] => ({
    title: `${row.subject_code === "PHY" ? "Physics" : "Chemistry"} Sample Paper ${row.code.slice(-3, -2)}-${row.code.slice(-2)}`,
    tier: "E",
    number: Number(row.code.slice(-2)),
    full_marks: 70,
    pass_marks: 21,
    time_text: "3 hours",
    is_published: true,
    is_sample: false,
    questions: 0,
    drafts: 0,
    header_json: { lines: ["Answer every question."], allotment: [] },
    tree: [],
    ...row,
  });
  const papers = [
    paper({ id: 2201, code: "PHY-E01", book: 2101, book_title: books[0].title, subject_code: "PHY", is_sample: true }),
    paper({ id: 2202, code: "PHY-E02", book: 2101, book_title: books[0].title, subject_code: "PHY" }),
    paper({
      id: 2203,
      code: "CHE-E01",
      book: 2102,
      book_title: books[1].title,
      subject_code: "CHE",
      is_published: false,
    }),
  ];
  const review = (
    row: Partial<S["ContentReviewDetail"]> &
      Pick<S["ContentReviewDetail"], "id" | "label" | "kind" | "target_id" | "paper" | "question">,
  ): S["ContentReviewDetail"] => ({
    subject: "PHY",
    stage: "check",
    state: "in_progress",
    assignee: null,
    submitted_by: editor,
    edited_by: editor,
    approved_by: null,
    approved_at: null,
    published_by: null,
    published_at: null,
    rolled_back_by: null,
    rolled_back_at: null,
    created: at(-5),
    fields_changed: [],
    yours: false,
    draft: {},
    previous: {},
    comments: [],
    changes: [],
    ...row,
  });
  const reviews = [
    review({
      id: 2501,
      label: "PHY-E01 2(c), solution",
      kind: "solution",
      target_id: 2402,
      paper: 2201,
      question: 2302,
      draft: { body_md: FIXED },
      created: at(-30),
    }),
    review({
      id: 2502,
      label: "PHY-E01 2(c), question",
      kind: "question",
      target_id: 2302,
      paper: 2201,
      question: 2302,
      state: "approved",
      stage: "publish",
      approved_by: reviewer,
      approved_at: at(-2),
      draft: questions[1].draft,
      created: at(-20),
    }),
    review({
      id: 2503,
      label: "CHE-E01 1(a), solution",
      kind: "solution",
      target_id: 2405,
      paper: 2203,
      question: 2305,
      subject: "CHE",
      state: "needs_changes",
      draft: { body_md: "**Ans.** Chlorine *(1)*" },
      comments: [
        {
          author: reviewer,
          text: "Chlorine at the anode only for brine: say which electrolyte.",
          at: at(-3),
          field: "body_md",
        },
      ],
      created: at(-50),
    }),
    review({
      id: 2504,
      label: "PHY-E02 1(a), solution",
      kind: "solution",
      target_id: 2404,
      paper: 2202,
      question: 2304,
      state: "approved",
      stage: "publish",
      approved_by: reviewer,
      approved_at: at(-30),
      published_by: reviewer,
      published_at: at(-30),
      draft: { body_md: SOLUTION },
      previous: { body_md: SOLUTION.replace("0.5", "5") },
      created: at(-60),
    }),
    review({
      id: 2505,
      label: "PHY-E01 3, solution",
      kind: "solution",
      target_id: 2403,
      paper: 2201,
      question: 2303,
      state: "cancelled",
      draft: { body_md: "draft withdrawn" },
      created: at(-90),
      comments: [
        { author: editor, text: "The draft changed after it was submitted: submit it again.", at: at(-89), field: "" },
      ],
    }),
  ];
  const report = (
    row: Partial<S["ContentReportDetail"]> & Pick<S["ContentReportDetail"], "id">,
  ): S["ContentReportDetail"] => ({
    kind: "solution",
    target_id: 2402,
    subject: "PHY",
    paper: 2201,
    paper_code: "PHY-E01",
    question: 2302,
    question_label: "2(c)",
    step: 2,
    printing: "PHY-2027-1",
    category: "wrong_answer",
    note: "",
    email: "",
    reporter: null,
    teacher_verified: false,
    state: "reported",
    fixed_in: "",
    fixed_at: null,
    resolved_at: null,
    staff_note: "",
    reporter_told_at: null,
    public: false,
    created: at(-10),
    can_tell: false,
    handled_by: null,
    linked: { paper_id: 2201, question_id: 2302, solution_id: 2402 },
    ...row,
  });
  const reports = [
    report({ id: 2601, note: "Step 2 gives 5 A; 6/12 is 0.5 A.", email: "re•••@example.com", created: at(-48) }),
    report({
      id: 2602,
      category: "typo",
      target_id: 2401,
      question: 2301,
      question_label: "1(a)",
      step: null,
      state: "confirmed",
      teacher_verified: true,
      reporter: 7101,
      resolved_at: at(-20),
      note: "Equipotential is spelt wrongly in the 2026 printing.",
      linked: { paper_id: 2201, question_id: 2301, solution_id: 2401 },
    }),
    report({
      id: 2603,
      state: "rejected",
      category: "marks",
      staff_note: "The marking scheme gives 1 mark there.",
      resolved_at: at(-5),
    }),
    report({
      id: 2604,
      state: "fixed_online",
      fixed_at: at(-2),
      resolved_at: at(-6),
      public: true,
      email: "ma•••@example.com",
      can_tell: true,
    }),
    report({
      id: 2605,
      state: "fixed_in_printing",
      fixed_at: at(-200),
      fixed_in: "PHY-2027-2",
      resolved_at: at(-210),
      public: true,
      reporter_told_at: at(-190),
      created: at(-220),
    }),
    report({
      id: 2606,
      kind: "quiz_item",
      target_id: 61,
      paper: null,
      paper_code: null,
      question: null,
      question_label: null,
      step: null,
      printing: "",
      category: "item_analysis",
      note: "Item analysis of 40 learners: 97% right, discrimination 0.05; flags: too_easy, low_discrimination",
      linked: { paper_id: null, question_id: null, solution_id: null, title: "Which of these is a vector?" },
    }),
    report({
      id: 2607,
      kind: "clip",
      target_id: 41,
      paper: null,
      paper_code: null,
      question: null,
      question_label: null,
      step: null,
      printing: "",
      category: "display",
      note: "The formula does not show on my phone.",
      linked: { paper_id: null, question_id: null, solution_id: null, title: "Coulomb's law in one picture" },
    }),
  ];
  const deposits: S["LegalDeposit"][] = [
    {
      id: 2701,
      book: 2101,
      book_title: books[0].title,
      edition: "First edition, 2026",
      library: "national_library",
      sent_on: day(-30),
      proof: "Speed Post EA123456789IN",
      has_file: false,
      erp_delivery_note: "",
      created_by: editor,
      created: at(-720),
    },
  ];
  const version = (
    id: number,
    hours: number,
    type: "+" | "~",
    reason: string,
    changes: S["ContentChange"][],
  ): S["ContentVersion"] => ({
    id,
    at: at(hours),
    by: type === "+" ? null : editor,
    reason,
    type,
    changes,
  });
  const versions: Record<string, S["ContentVersion"][]> = {
    "solutions:2402": [
      version(2902, -30, "~", "draft saved", [change("draft.body_md", "", FIXED)]),
      version(2901, -900, "+", "import_papers", []),
    ],
    "solutions:2404": [
      version(2912, -720, "~", "published (review #2504)", [change("body_md", SOLUTION.replace("0.5", "5"), SOLUTION)]),
      version(2911, -900, "+", "import_papers", []),
    ],
    "books:2101": [
      version(2922, -960, "~", "changed in the panel", [change("isbn", "", "9780306406157")]),
      version(2921, -1000, "+", "import_papers", []),
    ],
  };
  const world: ContentWorld = { books, papers, questions, solutions, reviews, reports, deposits, versions };
  const job = (id: number, dry: boolean, hours: number): MockJob => ({
    id,
    kind: "content_import",
    state: "done",
    dry_run: dry,
    params: { subject: "physics", commit: "", fixtures: false, ...(dry ? {} : { dry_run_job: id - 1 }) },
    done: 30,
    total: 30,
    errors: [],
    result: {
      subject: "physics",
      commit: "0e64cdf3a1b2c4d5e6f708192a3b4c5d6e7f8091",
      source: "repository",
      papers: 30,
      questions: 1650,
      counts: { created: 0, updated: 3, unchanged: 3328, unmatched: 0, removed: 1 },
      rows: {
        created: [],
        updated: ["PHY-E01 2(c): solution", "PHY-M04 7: question", "PHY-H02 9(b): solution"],
        unmatched: [],
        removed: ["PHY-E05 4 OR: question no longer in the repository"],
      },
    },
    result_url: null,
    change_request_id: null,
    cancel_requested: false,
    started_by: reviewer,
    created: at(hours),
    started_at: at(hours),
    finished_at: at(hours + 0.01),
    _ticks: 0,
    _rows: [],
  });
  return { world, jobs: [job(2802, false, -26), job(2801, true, -27)] };
}

// ---- The answers ----

/** The permission a content path needs, as content/staff_api.py names it; null: not a content path. */
export function contentPermission(method: string, parts: string[]): string {
  const [, area, id, verb] = parts;
  const get = method === "GET";
  switch (area) {
    case "summary":
    case "errata":
      return "content.view_errorreport";
    case "imports":
      return "content.view_paper";
    case "books":
    case "papers":
    case "questions":
    case "solutions": {
      const model = area.slice(0, -1);
      if (get) return `content.view_${model}`;
      if (!id) return `content.add_${model}`;
      if (verb === "rollback") return "staff.publish_paper";
      return `content.change_${model}`;
    }
    case "reviews":
      return get ? "content.view_reviewtask" : "staff.publish_paper";
    case "reports":
      return get ? "content.view_errorreport" : "staff.triage_report";
    case "legal-deposits":
      return get ? "content.view_legaldeposit" : "content.add_legaldeposit";
  }
  return "staff.view_system";
}

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const byId = <T extends { id: number }>(rows: T[], id: string | undefined) => rows.find((row) => String(row.id) === id);
const now = () => new Date().toISOString();

/** content/latex.py's first rule, as far as the mock goes: every $ that opens maths closes on its line. */
function latexProblems(value: string): string[] {
  const found: string[] = [];
  value.split("\n").forEach((line, index) => {
    const dollars = line.replace(/\\\$|\$\$/g, "").match(/\$/g)?.length ?? 0;
    if (dollars % 2) found.push(`Line ${index + 1}: $ opens maths and nothing closes it.`);
  });
  return found;
}

function treeOf(world: ContentWorld, paperId: number): S["ContentTreeQuestion"][] {
  return world.questions
    .filter((row) => row.paper === paperId)
    .sort((a, b) => a.order - b.order)
    .map((row) => {
      const solution = world.solutions.find((each) => each.question === row.id);
      return {
        id: row.id,
        order: row.order,
        label: row.label,
        number: row.number,
        group_label: row.group_label,
        part_label: row.part_label,
        is_alternative: row.is_alternative,
        marks_text: row.marks_text,
        is_published: row.is_published,
        state: row.state,
        preview: row.preview,
        solution: solution ? { id: solution.id, state: solution.state } : null,
      };
    });
}

function paperOf(world: ContentWorld, row: S["ContentPaperDetail"]): S["ContentPaperDetail"] {
  const tree = treeOf(world, row.id);
  const drafts = tree.filter(
    (each) => each.state !== "published" || (each.solution && each.solution.state !== "published"),
  ).length;
  return { ...row, tree, questions: tree.filter((each) => each.is_published).length, drafts };
}

function missingOf(world: ContentWorld): S["MissingDeposit"][] {
  const today = new Date().toISOString().slice(0, 10);
  return world.books
    .filter((book) => book.published_on)
    .map((book) => {
      const sent = world.deposits
        .filter((row) => row.book === book.id && row.edition === book.edition)
        .map((row) => row.library);
      const due = new Date(Date.parse(book.published_on!) + 30 * 86_400_000).toISOString().slice(0, 10);
      return {
        book: book.id,
        title: book.title,
        edition: book.edition ?? "",
        subject: book.subject_code,
        published_on: book.published_on!,
        due_on: due,
        overdue: due < today,
        missing: LIBRARIES.filter((library) => !sent.includes(library)),
      };
    })
    .filter((row) => row.missing.length);
}

const OPEN_REVIEW = (task: S["ContentReviewDetail"]) =>
  task.state === "in_progress" || (task.state === "approved" && !task.published_at);
const OPEN_REPORT = ["reported", "confirmed"];

export function contentRoute(t: Tools): Response {
  const { method, parts, body, url, me, world } = t;
  const [, area, id, verb, extra, more] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const reviewOut = (task: S["ContentReviewDetail"]) => {
    const target = (task.kind === "solution" ? world.solutions : world.questions).find(
      (row) => row.id === task.target_id,
    );
    const draft = (task.draft ?? {}) as Record<string, unknown>;
    return {
      ...task,
      yours: task.submitted_by === me || task.edited_by === me,
      fields_changed: Object.keys(draft),
      // the draft against the live text; once published, the text it replaced against it
      changes: task.published_at
        ? Object.entries(draft).map(([field, value]) =>
            change(field, (task.previous as Record<string, unknown>)?.[field] ?? "", value),
          )
        : target
          ? Object.entries(draft).map(([field, value]) =>
              change(field, (target as Record<string, unknown>)[field], value),
            )
          : [],
    };
  };

  switch (area) {
    case "summary": {
      if (method !== "GET") return t.notFound();
      const open = world.reports.filter((row) => OPEN_REPORT.includes(row.state));
      const byCategory: Record<string, number> = {};
      for (const row of open) byCategory[row.category] = (byCategory[row.category] ?? 0) + 1;
      const waiting = world.reviews.filter(OPEN_REVIEW);
      const mine = waiting.filter(
        (task) => task.submitted_by !== me && task.edited_by !== me && (!task.assignee || task.assignee === me),
      );
      const drafts = [...world.questions, ...world.solutions].filter((row) => row.state !== "published").length;
      const imports = t.jobs.filter((job) => job.kind === "content_import");
      return t.json(200, {
        reports_open: { total: open.length, by_category: byCategory },
        reviews_waiting: t.can("content.view_reviewtask") ? waiting.length : null,
        reviews_mine: t.can("content.view_reviewtask") && t.can("staff.publish_paper") ? mine.length : null,
        drafts: t.can("content.view_solution") ? drafts : null,
        legal_deposits_missing: t.can("content.view_legaldeposit") ? missingOf(world) : null,
        last_import: t.can("content.view_paper") ? (imports[0] ?? null) : null,
      });
    }

    case "books": {
      if (method === "GET" && !id) {
        const rows = world.books.filter(
          (book) =>
            (!query("subject") || book.subject_code === query("subject")) &&
            (!query("format") || book.format === query("format")),
        );
        return t.paginate(rows);
      }
      if (method === "POST" && !id) {
        const fields: Record<string, string[]> = {};
        for (const name of ["title", "slug"]) if (!text(body[name])) fields[name] = ["This field is required."];
        if (Object.keys(fields).length) return t.invalid(fields);
        const subject = world.books.find((book) => book.subject === Number(body.subject));
        const book: S["ContentBookDetail"] = {
          id: t.nextId(),
          title: text(body.title),
          subject: Number(body.subject),
          subject_code: subject?.subject_code ?? "PHY",
          edition: text(body.edition),
          slug: text(body.slug),
          cover: text(body.cover),
          isbn: text(body.isbn).replace(/[\s-]/g, ""),
          format: (text(body.format) || "print") as "print" | "ebook",
          published_on: text(body.published_on) || null,
          deposit_due_on: null,
          papers: 0,
          missing_deposits: [...LIBRARIES],
        };
        world.books.unshift(book);
        t.record("content.book_created", t.target("content.book", book.id, `Book #${book.id}`));
        return t.json(201, book);
      }
      const book = byId(world.books, id);
      if (!book) return t.notFound();
      if (method === "GET" && !verb) return t.json(200, book);
      if (method === "GET" && verb === "history") return t.paginate(world.versions[`books:${book.id}`] ?? []);
      if (method === "PATCH" && !verb) {
        const isbn = text(body.isbn).replace(/[\s-]/g, "");
        if ("isbn" in body && isbn && !/^97[89]\d{10}$/.test(isbn))
          return t.invalid({
            isbn: [
              "Not a valid ISBN-13: 13 digits starting 978 or 979, the last one its check digit (hyphens may stay).",
            ],
          });
        for (const key of ["title", "edition", "slug", "cover", "format", "published_on"] as const)
          if (key in body) (book as Record<string, unknown>)[key] = body[key] || (key === "published_on" ? null : "");
        if ("isbn" in body) book.isbn = isbn;
        t.record("content.book_changed", t.target("content.book", book.id, `Book #${book.id}`));
        return t.json(200, book);
      }
      if (method === "POST" && verb === "history" && more === "restore") {
        if (!byId(world.versions[`books:${book.id}`] ?? [], extra)) return t.notFound();
        t.record("content.version_restored", t.target("content.book", book.id, `Book #${book.id}`));
        return t.json(200, book);
      }
      return t.notFound();
    }

    case "papers": {
      if (method === "GET" && !id) {
        const rows = world.papers
          .map((row) => paperOf(world, row))
          .filter(
            (row) =>
              (!query("subject") || row.subject_code === query("subject")) &&
              (!query("tier") || row.tier === query("tier")) &&
              (!query("q") || `${row.code} ${row.title}`.toLowerCase().includes(query("q").toLowerCase())) &&
              (!query("changed") || row.drafts > 0 === (query("changed") === "true")) &&
              (!query("is_published") || row.is_published === (query("is_published") === "true")),
          );
        return t.paginate(rows);
      }
      const row = byId(world.papers, id);
      if (!row) return t.notFound();
      if (method === "GET" && !verb) return t.json(200, paperOf(world, row));
      if (method === "GET" && verb === "qr") {
        const printing = query("printing").trim();
        if (printing && !PRINTING.test(printing))
          return t.invalid({ printing: ["A print run's label: letters, digits and hyphens, PHY-2027-1."] });
        return t.json(200, {
          url: `https://examleaf.in/s/${row.code}/${printing ? `?printing=${printing}` : ""}`,
          png: PNG,
        });
      }
      if (method === "GET" && verb === "history") return t.paginate(world.versions[`papers:${row.id}`] ?? []);
      if (method === "PATCH" && !verb) {
        if (("is_published" in body || "is_sample" in body) && !t.can("staff.publish_paper"))
          return t.refuse("staff.publish_paper");
        for (const key of ["title", "time_text", "is_published", "is_sample"] as const)
          if (key in body) (row as Record<string, unknown>)[key] = body[key];
        const what = "is_published" in body ? (body.is_published ? "published" : "unpublished") : "changed";
        t.record(`content.paper_${what}`, t.target("content.paper", row.id, row.code));
        return t.json(200, paperOf(world, row));
      }
      return t.notFound();
    }

    case "questions":
    case "solutions": {
      const rows: (S["ContentQuestionDetail"] | S["ContentSolutionDetail"])[] =
        area === "questions" ? world.questions : world.solutions;
      if (method === "GET" && !id) return t.paginate(rows);
      const row = byId(rows, id);
      if (!row) return t.notFound();
      const kind = area === "questions" ? "question" : "solution";
      const label = `${row.paper_code} ${"label" in row ? row.label : row.question_label}, ${kind}`;
      const where = t.target(`content.${kind}`, row.id, label);
      const openTask = () =>
        world.reviews.find((task) => task.kind === kind && task.target_id === row.id && OPEN_REVIEW(task));
      const out = () => {
        const task = openTask();
        return { ...row, review: task ? { id: task.id, state: task.state, stage: task.stage } : null };
      };
      const draft = () => (row.draft ?? {}) as Record<string, unknown>;
      if (method === "GET" && !verb) return t.json(200, out());
      if (method === "GET" && verb === "history") return t.paginate(world.versions[`${area}:${row.id}`] ?? []);
      if (method === "PATCH" && !verb) {
        const fields = area === "solutions" ? ["body_md"] : ["text_md", "table_md", "options_json", "marks_text"];
        const problems: Record<string, string[]> = {};
        for (const field of fields) {
          const value = body[field];
          const found = typeof value === "string" ? latexProblems(value) : [];
          if (found.length) problems[field] = found;
        }
        if (Object.keys(problems).length) return t.invalid(problems);
        const next = { ...draft() };
        for (const field of fields)
          if (field in body) {
            const live = (row as Record<string, unknown>)[field];
            if (JSON.stringify(body[field]) === JSON.stringify(live)) delete next[field];
            else next[field] = body[field];
          }
        if ("tags" in body && Array.isArray(body.tags) && "tags" in row) row.tags = body.tags.map(String);
        if (JSON.stringify(next) === JSON.stringify(draft())) return t.json(200, out());
        const task = openTask(); // a changed draft leaves the review it waited in
        if (task) {
          task.state = "cancelled";
          task.comments.push({
            author: me,
            text: "The draft changed after it was submitted: submit it again.",
            at: now(),
            field: "",
          });
        }
        row.draft = next;
        row.state = Object.keys(next).length ? "draft" : "published";
        row.draft_by = Object.keys(next).length ? me : null;
        t.record("content.draft_saved", { ...where, details: { fields: Object.keys(next) } });
        return t.json(200, out());
      }
      if (method !== "POST") return t.notFound();
      if (verb === "submit") {
        if (row.state === "in_review") return t.invalid({ non_field_errors: ["It waits for review already."] });
        if (!Object.keys(draft()).length)
          return t.invalid({ non_field_errors: ["Nothing to submit: there is no change since the last publish."] });
        const task: S["ContentReviewDetail"] = {
          id: t.nextId(),
          label,
          kind,
          target_id: row.id,
          subject: row.paper_code.slice(0, 3),
          paper: row.paper,
          question: "label" in row ? row.id : row.question,
          stage: "check",
          state: "in_progress",
          assignee: null,
          submitted_by: me,
          edited_by: row.draft_by,
          approved_by: null,
          approved_at: null,
          published_by: null,
          published_at: null,
          rolled_back_by: null,
          rolled_back_at: null,
          created: now(),
          fields_changed: Object.keys(draft()),
          yours: true,
          draft: { ...draft() },
          previous: {},
          comments: [],
          changes: [],
        };
        world.reviews.unshift(task);
        row.state = "in_review";
        t.record("content.submitted", { ...where, details: { review: task.id } });
        return t.json(201, {
          id: task.id,
          state: task.state,
          stage: task.stage,
          assignee: null,
          submitted_by: me,
          created: task.created,
        });
      }
      if (verb === "discard") {
        if (!Object.keys(draft()).length)
          return t.invalid({ non_field_errors: ["There is no draft: the live text is the latest."] });
        const task = openTask();
        if (task) task.state = "cancelled";
        row.draft = {};
        row.state = "published";
        row.draft_by = null;
        t.record("content.draft_discarded", where);
        return t.json(200, out());
      }
      if (verb === "rollback") {
        const task = world.reviews.find(
          (each) => each.kind === kind && each.target_id === row.id && each.published_at && !each.rolled_back_at,
        );
        if (!task) return t.invalid({ non_field_errors: ["Nothing to roll back: no publish from the panel is live."] });
        const published = (task.draft ?? {}) as Record<string, unknown>;
        if (
          Object.entries(published).some(
            ([field, value]) => JSON.stringify((row as Record<string, unknown>)[field]) !== JSON.stringify(value),
          )
        )
          return t.invalid({
            non_field_errors: ["The live text changed since that publish: restore a version from the history instead."],
          });
        const previous = (task.previous ?? {}) as Record<string, unknown>;
        for (const [field, value] of Object.entries(previous)) (row as Record<string, unknown>)[field] = value;
        if (!Object.keys(draft()).length) row.draft = { ...((task.draft ?? {}) as Record<string, unknown>) };
        row.state = Object.keys(draft()).length ? "draft" : "published";
        task.rolled_back_at = now();
        task.rolled_back_by = me;
        t.record("content.rolled_back", { ...where, details: { review: task.id } });
        return t.json(200, out());
      }
      if (verb === "history" && more === "restore") {
        const found = byId(world.versions[`${area}:${row.id}`] ?? [], extra);
        if (!found) return t.notFound();
        t.record("content.version_restored", { ...where, details: { restored: found.id } });
        return t.json(200, out());
      }
      return t.notFound();
    }

    case "reviews": {
      if (method === "GET" && !id) {
        const rows = world.reviews.filter(
          (task) =>
            (query("mine") !== "true" ||
              (OPEN_REVIEW(task) &&
                task.submitted_by !== me &&
                task.edited_by !== me &&
                (!task.assignee || task.assignee === me))) &&
            (!query("open") || OPEN_REVIEW(task) === (query("open") === "true")) &&
            (!query("subject") || task.subject === query("subject")) &&
            (!query("state") || task.state === query("state")),
        );
        return t.paginate([...rows].sort((a, b) => a.id - b.id).map(reviewOut));
      }
      const task = byId(world.reviews, id);
      if (!task) return t.notFound();
      if (method === "GET" && !verb) return t.json(200, reviewOut(task));
      if (method !== "POST") return t.notFound();
      if (task.submitted_by === me || task.edited_by === me)
        return t.json(403, {
          detail: "You edited or submitted this draft: another reviewer checks and publishes it.",
          code: "own_edit",
        });
      const where = t.target("content.reviewtask", task.id, `Review task #${task.id}`);
      const comment = text(body.comment);
      const target = (task.kind === "solution" ? world.solutions : world.questions).find(
        (row) => row.id === task.target_id,
      );
      if (verb === "approve") {
        if (task.state !== "in_progress")
          return t.invalid({ non_field_errors: ["Only a review in progress is approved."] });
        Object.assign(task, { state: "approved", stage: "publish", approved_by: me, approved_at: now() });
        if (comment) task.comments.push({ author: me, text: comment, at: now(), field: "" });
        t.record("content.review_approved", where);
        return t.json(200, reviewOut(task));
      }
      if (verb === "needs-changes") {
        if (!comment) return t.invalid({ comment: ["This field may not be blank."] });
        if (!OPEN_REVIEW(task)) return t.invalid({ non_field_errors: ["Nothing to send back."] });
        Object.assign(task, { state: "needs_changes", stage: "check" });
        task.comments.push({ author: me, text: comment, at: now(), field: text(body.field) });
        if (target) target.state = "draft";
        t.record("content.review_needs_changes", where);
        return t.json(200, reviewOut(task));
      }
      if (verb === "publish") {
        if (!OPEN_REVIEW(task) || !target)
          return t.invalid({ non_field_errors: ["It is not open: nothing to publish."] });
        const draft = (task.draft ?? {}) as Record<string, unknown>;
        if (JSON.stringify(target.draft) !== JSON.stringify(draft))
          return t.invalid({ non_field_errors: ["The draft changed after it was submitted: it needs a new review."] });
        task.previous = Object.fromEntries(
          Object.keys(draft).map((field) => [field, (target as Record<string, unknown>)[field]]),
        );
        for (const [field, value] of Object.entries(draft)) (target as Record<string, unknown>)[field] = value;
        Object.assign(target, { draft: {}, state: "published", draft_by: null, published_at: now(), published_by: me });
        Object.assign(task, {
          state: "approved",
          stage: "publish",
          approved_by: task.approved_by ?? me,
          approved_at: task.approved_at ?? now(),
          published_by: me,
          published_at: now(),
        });
        t.record("content.published", {
          ...t.target(`content.${task.kind}`, task.target_id, task.label),
          details: { review: task.id },
        });
        return t.json(200, reviewOut(task));
      }
      return t.notFound();
    }

    case "reports": {
      if (method === "GET" && !id) {
        const rows = world.reports.filter(
          (row) =>
            (query("state") ? row.state === query("state") : OPEN_REPORT.includes(row.state)) &&
            (!query("category") || row.category === query("category")) &&
            (!query("subject") || row.subject === query("subject")) &&
            (!query("printing") || row.printing.toLowerCase() === query("printing").toLowerCase()) &&
            (query("teacher") !== "true" || row.teacher_verified),
        );
        return t.paginate([...rows].sort((a, b) => a.id - b.id));
      }
      const row = byId(world.reports, id);
      if (!row) return t.notFound();
      const where = t.target("content.errorreport", row.id, `Error report #${row.id}`);
      const refresh = () => ({
        ...row,
        can_tell:
          Boolean(row.email) && ["fixed_online", "fixed_in_printing"].includes(row.state) && !row.reporter_told_at,
      });
      if (method === "GET" && !verb) return t.json(200, refresh());
      if (method === "PATCH" && !verb) {
        if ("staff_note" in body) row.staff_note = text(body.staff_note);
        if ("public" in body) row.public = Boolean(body.public);
        t.record("content.report_changed", where);
        return t.json(200, refresh());
      }
      if (method !== "POST") return t.notFound();
      const steps: Record<string, [string[], S["ContentReportDetail"]["state"]]> = {
        confirm: [["reported"], "confirmed"],
        reject: [["reported", "confirmed"], "rejected"],
        "fix-online": [["reported", "confirmed"], "fixed_online"],
        "fix-in-printing": [["confirmed", "fixed_online"], "fixed_in_printing"],
        reopen: [["rejected"], "reported"],
      };
      if (verb === "tell") {
        if (!["fixed_online", "fixed_in_printing"].includes(row.state))
          return t.invalid({ non_field_errors: ["Tell the reporter once it is fixed."] });
        if (row.reporter_told_at) return t.invalid({ non_field_errors: ["The reporter was told already."] });
        if (!row.email) return t.invalid({ non_field_errors: ["No email address was left with this report."] });
        Object.assign(row, { reporter_told_at: now(), email: "" });
        t.record("content.reporter_told", where);
        return t.json(200, refresh());
      }
      const step = steps[verb ?? ""];
      if (!step) return t.notFound();
      if (!step[0].includes(row.state))
        return t.invalid({
          non_field_errors: [`It is ${row.state.replace(/_/g, " ")}: this step does not follow from there.`],
        });
      if ("staff_note" in body) row.staff_note = text(body.staff_note);
      if (verb === "reject" && !row.staff_note) return t.invalid({ staff_note: ["Say why it is not a mistake."] });
      if (verb === "fix-in-printing") {
        if (!PRINTING.test(text(body.fixed_in)))
          return t.invalid({ fixed_in: ["The printing that carries the fix: PHY-2027-2."] });
        row.fixed_in = text(body.fixed_in);
      }
      row.state = step[1];
      if (verb === "fix-online") row.fixed_at = now();
      if (verb === "reject") row.email = "";
      row.handled_by = me;
      t.record(`content.report_${verb!.replace(/-/g, "_")}`, where);
      return t.json(200, refresh());
    }

    case "errata": {
      const rows = world.reports
        .filter((row) => ["confirmed", "fixed_online", "fixed_in_printing"].includes(row.state))
        .filter(
          (row) =>
            (!query("book") ||
              String(world.papers.find((paper) => paper.id === row.paper)?.book ?? "") === query("book")) &&
            (!query("printing") || row.printing.toLowerCase() === query("printing").toLowerCase()) &&
            (!query("public") || row.public === (query("public") === "true")),
        )
        .map((row) => ({
          id: row.id,
          book: world.papers.find((paper) => paper.id === row.paper)?.book ?? null,
          paper_code: row.paper_code,
          question_label: row.question_label,
          step: row.step,
          category: row.category,
          printing: row.printing,
          state: row.state,
          fixed_in: row.fixed_in,
          fixed_at: row.fixed_at,
          public: row.public,
          created: row.created,
        }));
      return t.paginate(rows);
    }

    case "imports":
      return t.paginate(t.jobs.filter((job) => job.kind === "content_import"));

    case "legal-deposits": {
      if (method === "GET" && id === "missing") return t.json(200, missingOf(world));
      if (method === "GET" && !id) return t.paginate(world.deposits);
      if (method === "POST" && !id) {
        const fields: Record<string, string[]> = {};
        for (const name of ["book", "library", "sent_on", "proof"])
          if (!text(body[name])) fields[name] = ["This field is required."];
        if (Object.keys(fields).length) return t.invalid(fields);
        const book = world.books.find((row) => String(row.id) === text(body.book));
        if (!book) return t.invalid({ book: ["Not one of your subjects' books."] });
        if (text(body.sent_on) > new Date().toISOString().slice(0, 10))
          return t.invalid({ sent_on: ["Not a day to come: the day it went."] });
        const edition = text(body.edition) || book.edition || "";
        if (
          world.deposits.some(
            (row) => row.book === book.id && row.edition === edition && row.library === text(body.library),
          )
        )
          return t.invalid({ library: ["This library has this edition already."] });
        const deposit: S["LegalDeposit"] = {
          id: t.nextId(),
          book: book.id,
          book_title: book.title,
          edition,
          library: text(body.library) as S["LegalDeposit"]["library"],
          sent_on: text(body.sent_on),
          proof: text(body.proof),
          has_file: Boolean(body.proof_file),
          erp_delivery_note: text(body.erp_delivery_note),
          created_by: me,
          created: now(),
        };
        world.deposits.unshift(deposit);
        book.missing_deposits = book.missing_deposits.filter((library) => library !== deposit.library);
        t.record("content.legal_deposit_recorded", {
          ...t.target("content.book", book.id, `Book #${book.id}`),
          details: { library: deposit.library },
        });
        return t.json(201, deposit);
      }
      const row = byId(world.deposits, id);
      if (!row) return t.notFound();
      if (method === "GET" && !verb) return t.json(200, row);
      if (method === "GET" && verb === "proof")
        return row.has_file
          ? t.json(200, { file: "proof.pdf" })
          : t.json(404, { detail: "No scan was kept with this deposit.", code: "not_found" });
      return t.notFound();
    }
  }
  return t.notFound();
}

/** POST jobs/ with kind content_import (staff.import_content): a dry run, or the apply of one (its job named). */
export function startContentImport(t: Tools): Response | MockJob {
  if (!t.can("staff.import_content")) return t.refuse("staff.import_content");
  const params = (t.body.params ?? {}) as Body;
  const subject = text(params.subject);
  if (!["physics", "chemistry", "mathematics", "biology"].includes(subject))
    return t.invalid({ params: { subject: ["One of physics, chemistry, mathematics, biology."] } });
  const commit = text(params.commit).toLowerCase();
  if (commit && !/^[0-9a-f]{7,40}$/.test(commit))
    return t.invalid({
      params: { commit: ["A commit's hash: 7 to 40 of 0-9 and a-f; empty for the folder as it is."] },
    });
  const dry = t.body.dry_run === true;
  if (!dry) {
    const earlier = t.jobs.find(
      (job) =>
        job.id === Number(params.dry_run_job) && job.kind === "content_import" && job.dry_run && job.state === "done",
    );
    const same =
      earlier && (earlier.params as Body).subject === subject && ((earlier.params as Body).commit ?? "") === commit;
    if (!same)
      return t.invalid({
        params: { dry_run_job: ["Run a dry run of this subject and commit first; its apply follows within 24 hours."] },
      });
  }
  const result = {
    subject,
    commit: commit || "0e64cdf3a1b2c4d5e6f708192a3b4c5d6e7f8091",
    source: params.fixtures ? "fixtures" : "repository",
    papers: 30,
    questions: 1650,
    counts: { created: 0, updated: 2, unchanged: 3329, unmatched: 0, removed: 0 },
    rows: { created: [], updated: ["PHY-E01 2(c): solution", "PHY-E03 5: question"], unmatched: [], removed: [] },
  };
  const job: MockJob = {
    id: t.nextId(),
    kind: "content_import",
    state: "running",
    dry_run: dry,
    params: {
      subject,
      commit,
      fixtures: params.fixtures === true,
      ...(dry ? {} : { dry_run_job: Number(params.dry_run_job) }),
    },
    done: 0,
    total: 30,
    errors: [],
    result: {},
    result_url: null,
    change_request_id: null,
    cancel_requested: false,
    started_by: t.me,
    created: now(),
    started_at: now(),
    finished_at: null,
    _ticks: 0,
    _rows: [],
    _result: result,
  };
  t.jobs.unshift(job);
  t.record("job.requested", t.target("staff.job", job.id, `Job #${job.id}`));
  return job;
}
