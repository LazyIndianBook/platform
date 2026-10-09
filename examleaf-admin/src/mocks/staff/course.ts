// THE COURSE MODULE'S PART OF THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`;
// see handler.ts). Fixtures in the API's own shapes (learn/staff_api.py) holding every state the module draws: a
// subject whose chapters have a revision published, one in review by a colleague, one in review the person submitted
// (never theirs to decide), one approved and scheduled, a draft, and a chapter without one; clips ready, a free
// preview, one failed with its reason, one stuck processing, one with no video; cards and quiz items, each kind with
// one in the bin; items with their analysis under 30 learners (N/A), flagged, in the content triage; access open,
// ended and revoked, from each source, a child's; print runs being made, failed, ready, dispatched, void, and one from
// before the panel; codes unused, redeemed (by an adult, by a child) and void; a learner of each age. The answers keep
// the backend's rules: each path's permission (handler.ts), a recent authentication for making and voiding codes and
// for deleting, a reviewer never deciding their own submission (403 own_edit), the moves', the bin's and the access'
// refusals in the API's words, bulk jobs with a dry run (above the bulk limit waiting for an approver), 404 for what
// is not there; every learner's page and every redeemer shown is a sensitive read in the audit trail. Nothing here is
// used by the console's own code.
import type { MockJob, MockSchemas } from "./fixtures";
import type { Kit, SupportContext } from "./support-handler";

type S = MockSchemas;
type Body = Record<string, unknown>;
type Context = SupportContext;

type Chapter = {
  id: number;
  subject: number;
  number: number;
  title: string;
  weight: string;
  frequency: number;
  must_do: string;
};
type Revision = {
  id: number;
  chapter: number;
  title: string;
  target_minutes: number;
  status: S["CourseRevisionStatusEnum"];
  submitted_by: number | null;
  submitted_at: string | null;
  reviewer: number | null;
  publish_at: string | null;
  created: string;
  modified: string;
};
type Clip = {
  id: number;
  revision: number;
  order: number;
  title: string;
  kind: S["ClipKindEnum"];
  notes: string;
  is_free_preview: boolean;
  tags: string[];
  processing: S["ClipProcessingEnum"];
  reason: string;
  error_detail: string;
  processing_since: string;
  stuck: boolean;
  has_video: boolean;
  duration: number;
  questions: S["CourseClipQuestion"][];
  deleted_at: string | null;
  created: string;
  modified: string;
};
type Card = {
  id: number;
  chapter: number;
  order: number;
  front: string;
  back: string;
  tags: string[];
  deleted_at: string | null;
};
type Item = {
  id: number;
  chapter: number;
  order: number;
  kind: S["QuizItemKindEnum"];
  text: string;
  options: string[];
  answer: string;
  explanation: string;
  topic: string;
  marks: number;
  difficulty: S["QuizItemDifficultyEnum"] | "";
  bloom: S["QuizItemBloomEnum"] | "";
  tags: string[];
  source: S["CourseItemSource"] | null;
  stats: S["CourseItemStats"];
  flagged: number | null;
  deleted_at: string | null;
  history: S["CourseVersion"][];
};
type Entitlement = {
  id: number;
  user: number;
  subject: string | null;
  source: S["EntitlementSourceEnum"];
  reference: string;
  valid_until: string | null;
  note: string;
  revoked_at: string | null;
  created: string;
  modified: string;
  history: S["CourseVersion"][];
};
type Batch = {
  id: number;
  label: string;
  subject: string | null;
  product: S["CourseBatchProduct"] | null;
  printed: number;
  codes: number;
  redeemed: number;
  void: number;
  revoked: number;
  sold: number | null;
  note: string;
  created: string;
  generated_at: string | null;
  generated_by: number | null;
  dispatched_at: string | null;
  voided_at: string | null;
  void_reason: string;
  job: number | null;
  weeks: S["CourseWeek"][];
  signals: S["CourseBatchSignal"][];
  districts: S["CourseReportCell"][];
};
type Code = {
  code: string;
  batch: string;
  subject: string | null;
  redeemed_at: string | null;
  redeemed_by: number | null;
  voided_at: string | null;
};
type Learner = {
  id: number;
  name: string;
  email: string;
  is_minor: boolean;
  is_active: boolean;
  adult: boolean;
  summary: S["CourseLearnerSummary"];
  chapters: S["CourseLearnerChapter"][];
  devices: S["CourseLearnerDevice"][];
  tickets: S["CourseLearnerTicket"][];
};

export type CourseWorld = {
  subjects: { id: number; code: string; name: string }[];
  chapters: Chapter[];
  revisions: Revision[];
  clips: Clip[];
  cards: Card[];
  items: Item[];
  entitlements: Entitlement[];
  batches: Batch[];
  codes: Code[];
  learners: Learner[];
  /** Staff by id: who submitted, approved and made what. */
  people: Record<number, string>;
};

const DAY = 24 * 3_600_000;
const BIN_DAYS = 30;
const MIN_ANSWERS = 30;
const MIN_CELL = 10;
const LABEL = /^[A-Za-z0-9][A-Za-z0-9-]{0,39}$/;
const POSTER =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg==";
const COMPLETION = "A clip counts as watched once 90% of it has played, or the student marks it done.";
const SUBJECT_NAMES: Record<string, string> = { PHY: "Physics", CHE: "Chemistry", MAT: "Mathematics", BIO: "Biology" };
const STATUS_LABEL: Record<string, string> = {
  draft: "draft",
  review: "in review",
  approved: "approved",
  published: "published",
};
const PROCESSING_LABEL: Record<string, string> = {
  uploaded: "uploaded",
  processing: "processing",
  ready: "ready",
  failed: "failed",
};
// insights.FraudSignal.Kind's words for the code rules
const SIGNAL_LABEL: Record<string, string> = {
  codes_per_account: "one account redeeming many codes",
  codes_undispatched: "codes redeemed from a batch not yet dispatched (a leak)",
};

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const now = () => new Date().toISOString();
const day = (moment: number) => new Date(moment).toISOString().slice(0, 10);
const mask = (email: string) => email.replace(/^(.{2})[^@]*/, "$1•••");
const refusal = (message: string, field = "non_field_errors") => ({ [field]: [message] });
const binUntil = (deletedAt: string | null) =>
  deletedAt ? new Date(Date.parse(deletedAt) + BIN_DAYS * DAY).toISOString() : null;
const monday = (moment: string | null) => {
  if (!moment) return null;
  const date = new Date(moment);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
};

export function createCourse(at: (hours: number) => string, me: number, editor: number, reviewer: number) {
  const days = (count: number) => at(count * 24);
  const subjects = [
    { id: 1, code: "PHY", name: "Physics" },
    { id: 2, code: "CHE", name: "Chemistry" },
  ];
  const chapters: Chapter[] = [
    { id: 301, subject: 1, number: 1, title: "Electric charges and fields", weight: "8.0", frequency: 14, must_do: "" },
    {
      id: 302,
      subject: 1,
      number: 2,
      title: "Current electricity",
      weight: "7.0",
      frequency: 11,
      must_do: "Kirchhoff's two laws, and the **Wheatstone bridge** balance: $\\frac{P}{Q} = \\frac{R}{S}$.",
    },
    { id: 303, subject: 1, number: 3, title: "Moving charges and magnetism", weight: "6.0", frequency: 9, must_do: "" },
    { id: 304, subject: 1, number: 4, title: "Electromagnetic induction", weight: "6.0", frequency: 8, must_do: "" },
    { id: 305, subject: 1, number: 5, title: "Ray optics", weight: "9.0", frequency: 12, must_do: "" },
    { id: 311, subject: 2, number: 1, title: "Solutions", weight: "7.0", frequency: 10, must_do: "" },
  ];
  const revision = (row: Partial<Revision> & Pick<Revision, "id" | "chapter" | "title" | "status">): Revision => ({
    target_minutes: 12,
    submitted_by: null,
    submitted_at: null,
    reviewer: null,
    publish_at: null,
    created: days(-60),
    modified: days(-2),
    ...row,
  });
  const revisions: Revision[] = [
    revision({
      id: 401,
      chapter: 301,
      title: "Electric charges in 12 minutes",
      status: "published",
      submitted_by: editor,
      submitted_at: days(-20),
      reviewer,
    }),
    revision({
      id: 402,
      chapter: 302,
      title: "Current electricity, the whole chapter",
      status: "review",
      submitted_by: editor,
      submitted_at: days(-1),
    }),
    revision({
      id: 403,
      chapter: 303,
      title: "Magnetism without the fear",
      status: "approved",
      submitted_by: editor,
      submitted_at: days(-3),
      reviewer,
      publish_at: at(30),
    }),
    revision({
      id: 404,
      chapter: 304,
      title: "Induction: Faraday and Lenz",
      status: "review",
      submitted_by: me,
      submitted_at: days(-1),
    }),
    revision({ id: 411, chapter: 311, title: "Solutions, briefly", status: "draft" }),
  ];
  const clip = (row: Partial<Clip> & Pick<Clip, "id" | "revision" | "order" | "title">): Clip => ({
    kind: "concept",
    notes: "",
    is_free_preview: false,
    tags: [],
    processing: "ready",
    reason: "",
    error_detail: "",
    processing_since: days(-10),
    stuck: false,
    has_video: true,
    duration: 185,
    questions: [],
    deleted_at: null,
    created: days(-30),
    modified: days(-10),
    ...row,
  });
  const clips: Clip[] = [
    clip({
      id: 501,
      revision: 401,
      order: 1,
      title: "Coulomb's law",
      notes: "The force between two charges: $F = k\\frac{q_1 q_2}{r^2}$.",
      questions: [{ id: 8101, paper: "PHY-E01", label: "2(a)" }],
    }),
    clip({
      id: 502,
      revision: 401,
      order: 2,
      title: "Field lines",
      kind: "trick",
      is_free_preview: true,
      duration: 142,
    }),
    clip({ id: 503, revision: 401, order: 3, title: "Gauss's law, the shortcut", kind: "shortcut", duration: 236 }),
    clip({ id: 504, revision: 402, order: 1, title: "Ohm's law", duration: 160 }),
    clip({ id: 505, revision: 402, order: 2, title: "Kirchhoff's laws", kind: "formula", duration: 214 }),
    clip({
      id: 506,
      revision: 402,
      order: 3,
      title: "The Wheatstone bridge",
      kind: "pattern",
      processing: "failed",
      duration: 0,
      reason: "The video could not be read (cut short or damaged): export it again and upload it.",
      error_detail: "ffmpeg failed (exit 1): moov atom not found",
      processing_since: at(-5),
    }),
    clip({
      id: 507,
      revision: 403,
      order: 1,
      title: "Force on a moving charge",
      processing: "processing",
      duration: 0,
      stuck: true,
      reason: "It has been processing for over an hour: its task was probably lost when a worker stopped. Retry it.",
      processing_since: at(-3),
    }),
    clip({ id: 508, revision: 403, order: 2, title: "Biot-Savart in two minutes", duration: 128 }),
    clip({
      id: 509,
      revision: 404,
      order: 1,
      title: "Lenz's law",
      processing: "uploaded",
      has_video: false,
      duration: 0,
      reason: "No video yet: upload it on the clip's page in the admin.",
    }),
    clip({ id: 510, revision: 404, order: 2, title: "Eddy currents", kind: "mistake", duration: 175 }),
    clip({ id: 511, revision: 401, order: 4, title: "An old take of Coulomb's law", deleted_at: at(-30) }),
  ];
  const cards: Card[] = [
    {
      id: 601,
      chapter: 301,
      order: 1,
      front: "What is the SI unit of charge?",
      back: "The coulomb (C).",
      tags: [],
      deleted_at: null,
    },
    {
      id: 602,
      chapter: 301,
      order: 2,
      front: "State Coulomb's law.",
      back: "$F = k\\frac{q_1 q_2}{r^2}$",
      tags: ["formula"],
      deleted_at: null,
    },
    {
      id: 603,
      chapter: 301,
      order: 3,
      front: "What is an electric dipole?",
      back: "Two equal and opposite charges a small distance apart.",
      tags: [],
      deleted_at: null,
    },
    {
      id: 604,
      chapter: 302,
      order: 1,
      front: "Define drift velocity.",
      back: "The average velocity of the free electrons in a conductor.",
      tags: [],
      deleted_at: null,
    },
    {
      id: 605,
      chapter: 302,
      order: 2,
      front: "An old card on resistivity",
      back: "ρ = RA/l",
      tags: [],
      deleted_at: at(-50),
    },
  ];
  const stats = (n: number | null, p: number | null, discrimination: number | null, flags: string[] = []) => ({
    n,
    p,
    discrimination,
    flags,
    computed_at: n === null ? null : at(-6),
    n_too_small: n === null || n < MIN_ANSWERS,
  });
  const item = (row: Partial<Item> & Pick<Item, "id" | "chapter" | "order" | "text">): Item => ({
    kind: "mcq",
    options: ["(i) 1", "(ii) 2", "(iii) 3", "(iv) 4"],
    answer: "2",
    explanation: "",
    topic: "",
    marks: 1,
    difficulty: "",
    bloom: "",
    tags: [],
    source: null,
    stats: stats(null, null, null),
    flagged: null,
    deleted_at: null,
    history: [
      {
        id: row.id * 10,
        at: days(-40),
        by: editor,
        type: "+",
        reason: "the history starts here (Phase B)",
        changes: [],
      },
    ],
    ...row,
  });
  const items: Item[] = [
    item({
      id: 701,
      chapter: 301,
      order: 1,
      text: "Two charges of $2\\,\\mu C$ each are 1 m apart. The force between them is:",
      topic: "Coulomb's law",
      difficulty: "easy",
      bloom: "apply",
      source: { question: 8101, paper: "PHY-E01", label: "1(a)" },
      stats: stats(412, 0.81, 0.42),
    }),
    item({
      id: 702,
      chapter: 301,
      order: 2,
      kind: "true_false",
      text: "Field lines of a point charge can cross each other.",
      options: [],
      answer: "false",
      difficulty: "medium",
      bloom: "understand",
      stats: stats(388, 0.34, 0.08, ["low_discrimination", "distractor_2"]),
      flagged: 9301,
    }),
    item({
      id: 703,
      chapter: 301,
      order: 3,
      kind: "fill_blank",
      text: "The SI unit of electric flux is ____.",
      options: [],
      answer: "N m^2/C|Nm²/C",
      stats: stats(12, 0.5, 0.2),
    }),
    item({
      id: 704,
      chapter: 302,
      order: 1,
      text: "In a balanced Wheatstone bridge, the galvanometer current is:",
      difficulty: "hard",
      bloom: "remember",
      tags: ["bridge"],
      stats: stats(57, 0.93, 0.15, ["too_easy"]),
    }),
    item({ id: 705, chapter: 302, order: 2, text: "An old item on emf", deleted_at: at(-72) }),
  ];
  const ent = (row: Partial<Entitlement> & Pick<Entitlement, "id" | "user" | "subject" | "source">): Entitlement => ({
    reference: "",
    valid_until: null,
    note: "",
    revoked_at: null,
    created: days(-30),
    modified: days(-30),
    history: [],
    ...row,
  });
  const entitlements: Entitlement[] = [
    ent({ id: 801, user: 7101, subject: "PHY", source: "book_code", reference: "PHY-2027-1", created: days(-20) }),
    ent({ id: 802, user: 7102, subject: null, source: "purchase", valid_until: day(Date.now() + 200 * DAY) }),
    ent({
      id: 803,
      user: 7102,
      subject: "CHE",
      source: "grant",
      valid_until: day(Date.now() + 20 * DAY),
      reference: "T-2026-00042",
      note: "A lost book code: the bill and the book's photo checked.",
    }),
    ent({
      id: 804,
      user: 7103,
      subject: "CHE",
      source: "grant",
      valid_until: day(Date.now() - 10 * DAY),
      note: "A school's trial.",
    }),
    ent({
      id: 805,
      user: 7105,
      subject: "PHY",
      source: "grant",
      valid_until: day(Date.now() - DAY),
      revoked_at: days(-1),
      note: "Granted by mistake.",
    }),
  ];
  const physicsBook = { id: 2100, slug: "physics-sample-papers-2027", title: "Physics Sample Papers 2027" };
  const batch = (row: Partial<Batch> & Pick<Batch, "id" | "label" | "subject" | "printed">): Batch => ({
    product: null,
    codes: row.printed,
    redeemed: 0,
    void: 0,
    revoked: 0,
    sold: null,
    note: "",
    created: days(-40),
    generated_at: days(-40),
    generated_by: me,
    dispatched_at: null,
    voided_at: null,
    void_reason: "",
    job: null,
    weeks: [],
    signals: [],
    districts: [],
    ...row,
  });
  const batches: Batch[] = [
    batch({
      id: 2401,
      label: "PHY-2027-1",
      subject: "PHY",
      printed: 500,
      product: physicsBook,
      redeemed: 214,
      void: 3,
      revoked: 1,
      sold: 260,
      note: "Printed by Saraighat Offset, run of 500.",
      dispatched_at: days(-35),
      weeks: [
        { week: monday(days(-28)) ?? "", redeemed: 58 },
        { week: monday(days(-21)) ?? "", redeemed: 77 },
        { week: monday(days(-14)) ?? "", redeemed: 49 },
        { week: monday(days(-7)) ?? "", redeemed: 30 },
      ],
      signals: [
        {
          id: 2451,
          kind: "codes_per_account",
          label: SIGNAL_LABEL.codes_per_account,
          count: 6,
          window_start: days(-9),
          window_end: days(-8),
          created: days(-8),
          acknowledged_at: days(-7),
        },
      ],
      districts: [
        { district: "Kamrup Metropolitan", activated: 121, hidden: false },
        { district: "Dibrugarh", activated: 38, hidden: false },
        { district: "other districts", activated: null, hidden: true },
      ],
    }),
    batch({
      id: 2402,
      label: "CHE-2027-1",
      subject: "CHE",
      printed: 300,
      redeemed: 2,
      note: "For the Jorhat school order.",
      signals: [
        {
          id: 2452,
          kind: "codes_undispatched",
          label: SIGNAL_LABEL.codes_undispatched,
          count: 2,
          window_start: days(-2),
          window_end: days(-1),
          created: days(-1),
          acknowledged_at: null,
        },
      ],
      districts: [{ district: "other districts", activated: null, hidden: true }],
    }),
    batch({
      id: 2403,
      label: "PHY-2026-9",
      subject: "PHY",
      printed: 50,
      redeemed: 4,
      void: 46,
      dispatched_at: days(-100),
      voided_at: days(-60),
      void_reason: "A test print run that reached a shop.",
      created: days(-120),
      generated_at: days(-120),
    }),
    batch({ id: 2404, label: "MAT-2027-1", subject: "MAT", printed: 200, codes: 0, generated_at: null, job: 2481 }),
    batch({ id: 2405, label: "BIO-2027-1", subject: "BIO", printed: 100, codes: 0, generated_at: null, job: 2482 }),
    batch({
      id: 2406,
      label: "Spring 2026",
      subject: null,
      printed: 40,
      redeemed: 40,
      generated_by: null,
      created: days(-300),
      generated_at: days(-300),
      dispatched_at: days(-300),
      note: "Made before the panel: its dispatch date was not recorded.",
    }),
  ];
  const codes: Code[] = [
    {
      code: "7KQM-3XPA-9TRW",
      batch: "PHY-2027-1",
      subject: "PHY",
      redeemed_at: null,
      redeemed_by: null,
      voided_at: null,
    },
    {
      code: "4HNC-8DVE-2JYS",
      batch: "PHY-2027-1",
      subject: "PHY",
      redeemed_at: days(-20),
      redeemed_by: 7101,
      voided_at: null,
    },
    {
      code: "6PWT-5MBR-8GKD",
      batch: "PHY-2027-1",
      subject: "PHY",
      redeemed_at: days(-12),
      redeemed_by: 7102,
      voided_at: null,
    },
    {
      code: "9XZA-2QLF-7CHV",
      batch: "PHY-2026-9",
      subject: "PHY",
      redeemed_at: null,
      redeemed_by: null,
      voided_at: days(-60),
    },
    {
      code: "3RDS-6HJW-4NPB",
      batch: "CHE-2027-1",
      subject: "CHE",
      redeemed_at: null,
      redeemed_by: null,
      voided_at: null,
    },
  ];
  const chapterRow = (
    id: number,
    subject: string,
    number: number,
    title: string,
    counts: [number, number, number, number, number | null, number, number],
  ): S["CourseLearnerChapter"] => {
    const [watched, total, minutes, answers, accuracy, reviews, known] = counts;
    return {
      id,
      subject,
      number,
      title,
      clips_watched: watched,
      clips_total: total,
      minutes_watched: minutes,
      quiz_answers: answers,
      quiz_accuracy: accuracy,
      card_reviews: reviews,
      cards_known: known,
    };
  };
  const learners: Learner[] = [
    {
      id: 7101,
      name: "Riya Das",
      email: "riya.das@example.com",
      is_minor: true,
      is_active: true,
      adult: false,
      summary: {
        clips_watched: 3,
        minutes_watched: 9,
        quiz_answers: 12,
        quiz_accuracy: 75,
        card_reviews: 20,
        last_active: null,
        last_active_week: monday(days(-2)),
      },
      chapters: [chapterRow(301, "PHY", 1, "Electric charges and fields", [3, 3, 9, 12, 75, 20, 14])],
      devices: [{ id: 9701, platform: "android", added: null, last_seen: null, last_seen_week: monday(days(-2)) }],
      tickets: [],
    },
    {
      id: 7102,
      name: "Bikash Deka",
      email: "bikash.deka@example.com",
      is_minor: false,
      is_active: true,
      adult: true,
      summary: {
        clips_watched: 5,
        minutes_watched: 17,
        quiz_answers: 30,
        quiz_accuracy: 63,
        card_reviews: 8,
        last_active: at(-5),
        last_active_week: monday(at(-5)),
      },
      chapters: [
        chapterRow(301, "PHY", 1, "Electric charges and fields", [3, 3, 10, 18, 72, 5, 3]),
        chapterRow(302, "PHY", 2, "Current electricity", [2, 2, 7, 12, 50, 3, 1]),
      ],
      devices: [
        { id: 9702, platform: "ios", added: days(-40), last_seen: at(-5), last_seen_week: monday(at(-5)) },
        { id: 9703, platform: "android", added: days(-90), last_seen: days(-60), last_seen_week: monday(days(-60)) },
      ],
      tickets: [
        {
          number: "T-2026-00042",
          subject: "My book code says it was used",
          category: "course",
          status: "resolved",
          received_at: days(-12),
        },
      ],
    },
  ];
  const jobs: MockJob[] = [
    {
      id: 2481,
      kind: "code_batch",
      state: "running",
      dry_run: false,
      params: { batch: 2404, label: "MAT-2027-1", count: 200 },
      done: 60,
      total: 200,
      errors: [],
      result: {},
      result_url: null,
      change_request_id: null,
      cancel_requested: false,
      started_by: me,
      created: at(-0.1),
      started_at: at(-0.1),
      finished_at: null,
      _ticks: 0,
      _rows: Array.from({ length: 200 }, (_, index) => String(index)),
      _result: { batch: "MAT-2027-1", codes: 200 },
    },
    {
      id: 2482,
      kind: "code_batch",
      state: "failed",
      dry_run: false,
      params: { batch: 2405, label: "BIO-2027-1", count: 100 },
      done: 0,
      total: 100,
      errors: [{ id: 2405, label: "BIO-2027-1", message: "The storage did not answer: no code was kept." }],
      result: {},
      result_url: null,
      change_request_id: null,
      cancel_requested: false,
      started_by: me,
      created: days(-1),
      started_at: days(-1),
      finished_at: days(-1),
      _ticks: 0,
      _rows: [],
    },
  ];
  const people: Record<number, string> = { [me]: "You", [editor]: "Meera Bora", [reviewer]: "Arup Sharma" };
  const world: CourseWorld = {
    subjects,
    chapters,
    revisions,
    clips,
    cards,
    items,
    entitlements,
    batches,
    codes,
    learners,
    people,
  };
  return { world, jobs };
}

// ---- Which permission each path needs (learn/staff_api.py's `permissions` maps) ----

const MODELS: Record<string, string> = { clips: "clip", cards: "flashcard", items: "quizitem" };

export function coursePermission(context: Context): string {
  const { method, parts, url } = context;
  const [, area, id, verb] = parts;
  const get = method === "GET";
  switch (area) {
    case "subjects":
      return "learn.view_chapter";
    case "chapters":
      return get ? "learn.view_chapter" : "learn.change_chapter";
    case "revisions":
      if (get) return "learn.view_revision";
      return !verb || verb === "submit" ? "learn.change_revision" : "staff.publish_course";
    case "clips":
    case "cards":
    case "items": {
      const model = MODELS[area];
      if (get) return `learn.view_${model}`;
      if (method === "DELETE") return `learn.delete_${model}`;
      if (area === "items" && verb === "flag") return "staff.triage_report";
      return `learn.change_${model}`;
    }
    case "bin":
      return `learn.view_${MODELS[url.searchParams.get("kind") || "clips"] ?? "clip"}`;
    case "entitlements":
      if (get) return "learn.view_entitlement";
      return id ? "learn.change_entitlement" : "learn.add_entitlement";
    case "codes": {
      if (id === "lookup") return "learn.view_bookcode";
      if (id === "void") return "staff.void_book_codes";
      if (id === "report") return "learn.view_codebatch";
      if (get) return "learn.view_codebatch";
      if (!verb) return parts.length <= 3 ? "staff.make_book_codes" : "learn.view_codebatch";
      const action = parts[4];
      return action === "void" ? "staff.void_book_codes" : "learn.change_codebatch";
    }
    case "learners":
      return get ? "learn.view_entitlement" : "staff.end_user_sessions";
  }
  return "staff.view_system";
}

/** The permission a course bulk job needs: its action's maker's (staff.jobs.permission); null for another action. */
export function courseBulkPermission(params: unknown): string | null {
  const action = text((params as Body | null)?.action);
  const makers: Record<string, string> = {
    item_metadata: "learn.change_quizitem",
    "entitlement.grant": "learn.add_entitlement",
    "entitlement.extend": "learn.change_entitlement",
    "entitlement.revoke": "learn.change_entitlement",
  };
  return makers[action] ?? null;
}

// ---- The answers' shapes ----

const live = <T extends { deleted_at: string | null }>(rows: T[]) => rows.filter((row) => !row.deleted_at);
const byOrder = <T extends { order: number; id: number }>(rows: T[]) =>
  [...rows].sort((a, b) => a.order - b.order || a.id - b.id);
const person = (world: CourseWorld, id: number | null) => (id ? { id, name: world.people[id] ?? `#${id}` } : null);
const subjectCode = (world: CourseWorld, chapter: Chapter) =>
  world.subjects.find((subject) => subject.id === chapter.subject)?.code ?? "PHY";
const chapterOf = (world: CourseWorld, id: number) => world.chapters.find((chapter) => chapter.id === id)!;
const preview = (value: string) => (value.length > 120 ? `${value.slice(0, 119)}…` : value);

function revisionClips(world: CourseWorld, revision: Revision): S["CourseOutlineClip"][] {
  const rows = byOrder(live(world.clips.filter((clip) => clip.revision === revision.id)));
  return rows.map((clip, index) => ({
    id: clip.id,
    order: clip.order,
    title: clip.title,
    kind: clip.kind,
    duration: clip.duration,
    processing: clip.processing,
    reason: clip.reason,
    is_free_preview: clip.is_free_preview,
    free: clip.is_free_preview || index === 0,
  }));
}

const minutesOf = (world: CourseWorld, revision: Revision) =>
  Math.round(
    live(world.clips.filter((clip) => clip.revision === revision.id && clip.processing === "ready")).reduce(
      (sum, clip) => sum + clip.duration,
      0,
    ) / 60,
  );

function outline(world: CourseWorld, subject: number): S["CourseOutline"] | null {
  const found = world.subjects.find((each) => each.id === subject);
  const chapters = world.chapters.filter((chapter) => chapter.subject === subject).sort((a, b) => a.number - b.number);
  if (!found || !chapters.length) return null;
  return {
    subject: found,
    completion_rule: COMPLETION,
    free_preview: true,
    chapters: chapters.map((chapter) => {
      const revision = world.revisions.find((each) => each.chapter === chapter.id);
      return {
        ...chapter,
        revision: revision
          ? {
              id: revision.id,
              title: revision.title,
              status: revision.status,
              target_minutes: revision.target_minutes,
              minutes: minutesOf(world, revision),
              publish_at: revision.publish_at,
              clips: revisionClips(world, revision),
            }
          : null,
        cards: byOrder(live(world.cards.filter((card) => card.chapter === chapter.id))).map((card) => ({
          id: card.id,
          order: card.order,
          front: preview(card.front),
        })),
        items: byOrder(live(world.items.filter((item) => item.chapter === chapter.id))).map((item) => ({
          id: item.id,
          order: item.order,
          kind: item.kind,
          text: preview(item.text),
          difficulty: item.difficulty,
          flagged: item.flagged,
        })),
      };
    }),
  };
}

function transitions(revision: Revision, me: number, can: (perm: string) => boolean): S["CourseTransitionEnum"][] {
  const own = revision.submitted_by === me;
  const review = can("staff.publish_course");
  const moves: S["CourseTransitionEnum"][] = [];
  if (revision.status === "draft" && can("learn.change_revision")) moves.push("submit");
  if (revision.status === "review" && review && !own) moves.push("approve", "needs_changes", "publish");
  if (revision.status === "approved" && review && !own) moves.push("publish");
  if (revision.status !== "draft" && review) moves.push("unpublish");
  return moves;
}

function revisionOut(world: CourseWorld, revision: Revision, me: number, can: (perm: string) => boolean) {
  const chapter = chapterOf(world, revision.chapter);
  return {
    ...revision,
    chapter: {
      id: chapter.id,
      number: chapter.number,
      title: chapter.title,
      subject: chapter.subject,
      subject_code: subjectCode(world, chapter),
    },
    status_label: STATUS_LABEL[revision.status],
    submitted_by: person(world, revision.submitted_by),
    reviewer: person(world, revision.reviewer),
    minutes: minutesOf(world, revision),
    clips: revisionClips(world, revision),
    cards: live(world.cards.filter((card) => card.chapter === chapter.id)).length,
    items: live(world.items.filter((item) => item.chapter === chapter.id)).length,
    transitions: transitions(revision, me, can),
  } satisfies S["CourseRevision"];
}

function clipOut(world: CourseWorld, clip: Clip): S["CourseClip"] {
  const revision = world.revisions.find((each) => each.id === clip.revision)!;
  const chapter = chapterOf(world, revision.chapter);
  const ready = clip.processing === "ready" && !clip.deleted_at;
  const first = byOrder(live(world.clips.filter((each) => each.revision === clip.revision)))[0];
  return {
    ...clip,
    revision: {
      id: revision.id,
      title: revision.title,
      status: revision.status,
      chapter: chapter.id,
      chapter_number: chapter.number,
      chapter_title: chapter.title,
      subject: chapter.subject,
      subject_code: subjectCode(world, chapter),
    },
    free: clip.is_free_preview || first?.id === clip.id,
    processing_label: PROCESSING_LABEL[clip.processing],
    can_retry: clip.has_video && !clip.deleted_at && (clip.processing === "failed" || clip.stuck),
    poster_url: ready ? POSTER : null,
    player_url: ready ? `/learn/preview/${clip.id}/` : null,
    bin_until: binUntil(clip.deleted_at),
    completion_rule: COMPLETION,
  };
}

function itemOut(world: CourseWorld, item: Item): S["CourseItem"] {
  const chapter = chapterOf(world, item.chapter);
  const { history, ...rest } = item;
  void history;
  return {
    ...rest,
    chapter: { id: chapter.id, number: chapter.number, title: chapter.title, subject: subjectCode(world, chapter) },
    bin_until: binUntil(item.deleted_at),
  };
}

function itemRow(world: CourseWorld, item: Item): S["CourseItemRow"] {
  const full = itemOut(world, item);
  return {
    id: full.id,
    chapter: full.chapter,
    order: full.order,
    kind: full.kind,
    text: preview(full.text),
    topic: full.topic ?? "",
    marks: full.marks ?? 1,
    difficulty: item.difficulty,
    bloom: item.bloom,
    tags: full.tags,
    source: full.source,
    stats: full.stats,
    flagged: full.flagged,
  };
}

function binRow(world: CourseWorld, kind: S["CourseRowKindEnum"], row: Clip | Card | Item): S["CourseBinRow"] {
  const chapterId =
    kind === "clips"
      ? world.revisions.find((each) => each.id === (row as Clip).revision)!.chapter
      : (row as Card | Item).chapter;
  const chapter = chapterOf(world, chapterId);
  return {
    id: row.id,
    kind,
    title:
      kind === "clips" ? (row as Clip).title : kind === "cards" ? (row as Card).front : preview((row as Item).text),
    chapter: { id: chapter.id, number: chapter.number, title: chapter.title, subject: subjectCode(world, chapter) },
    revision: kind === "clips" ? (row as Clip).revision : null,
    deleted_at: row.deleted_at ?? "",
    bin_until: binUntil(row.deleted_at) ?? "",
  };
}

function stateOf(entitlement: Entitlement): S["CourseEntitlementStateEnum"] {
  if (entitlement.revoked_at) return "revoked";
  return !entitlement.valid_until || entitlement.valid_until >= day(Date.now()) ? "active" : "ended";
}

function entitlementOut(context: Context, entitlement: Entitlement): S["CourseEntitlement"] {
  const user = context.world.users.find((each) => each.id === entitlement.user);
  const learner = context.world.course.learners.find((each) => each.id === entitlement.user);
  const { history, ...rest } = entitlement;
  void history;
  const state = stateOf(entitlement);
  return {
    ...rest,
    user: {
      id: entitlement.user,
      name: learner?.name ?? user?.full_name ?? "",
      email: learner ? mask(learner.email) : (user?.email ?? ""),
      is_minor: learner?.is_minor ?? Boolean(user?.under_18),
    },
    subject_name: entitlement.subject ? (SUBJECT_NAMES[entitlement.subject] ?? entitlement.subject) : "every subject",
    state,
    can_extend: !entitlement.revoked_at && entitlement.valid_until !== null,
    can_revoke: state === "active",
  };
}

const batchKey = (batch: Batch) => (LABEL.test(batch.label) ? batch.label : `~${batch.id}`);

function batchState(context: Context, batch: Batch): S["CourseBatchStateEnum"] {
  if (batch.voided_at) return "void";
  if (!batch.generated_at) {
    const job = context.world.jobs.find((each) => each.id === batch.job);
    if (job?.state === "done") {
      batch.generated_at = job.finished_at ?? now();
      batch.codes = batch.printed;
    } else return job && (job.state === "queued" || job.state === "running") ? "generating" : "failed";
  }
  return batch.dispatched_at ? "dispatched" : "ready";
}

function batchOut(context: Context, batch: Batch): S["CourseBatch"] {
  const state = batchState(context, batch);
  const job = context.world.jobs.find((each) => each.id === batch.job);
  return {
    id: batch.id,
    key: batchKey(batch),
    label: batch.label,
    subject: batch.subject,
    product: batch.product,
    printed: batch.printed,
    codes: batch.codes,
    redeemed: batch.redeemed,
    void: batch.void,
    state,
    note: batch.note,
    created: batch.created,
    generated_at: batch.generated_at,
    generated_by: person(context.world.course, batch.generated_by),
    dispatched_at: batch.dispatched_at,
    voided_at: batch.voided_at,
    void_reason: batch.void_reason,
    job: job ? { id: job.id, state: job.state, done: job.done, total: job.total } : null,
  };
}

function versionOf(
  at: string,
  by: number,
  type: "+" | "~" | "-",
  reason: string,
  changes: Record<string, unknown>,
): S["CourseVersion"] {
  return {
    id: Date.parse(at) % 1_000_000_000,
    at,
    by,
    type,
    reason,
    changes: Object.entries(changes).map(([field, pair]) => {
      const [before, after] = pair as [unknown, unknown];
      return { field, before, after };
    }),
  };
}

// ---- The rules each action keeps (learn/course.py), shared by the single paths and the bulk jobs ----

type Outcome = { ok: true; apply: () => void } | { ok: false; fields: Record<string, string[]> };
const refuse = (message: string, field?: string): Outcome => ({ ok: false, fields: refusal(message, field) });

function grantRule(context: Context, account: number, subject: string, until: string | null, reason: string): Outcome {
  const world = context.world;
  if (!world.users.some((user) => user.id === account)) return refuse("No such account.", "user");
  const code = subject.toUpperCase();
  if (code && code !== "ALL" && !SUBJECT_NAMES[code])
    return refuse(`No subject ${code}: PHY, CHE, MAT, BIO or ALL.`, "subject");
  if (until && until < day(Date.now())) return refuse("A day from today on, or none (no end).", "valid_until");
  if (until && until > day(Date.now() + 730 * DAY)) return refuse("Within two years, or none (no end).", "valid_until");
  const wanted = code === "ALL" || !code ? null : code;
  const open = world.course.entitlements.find(
    (row) =>
      row.user === account &&
      stateOf(row) === "active" &&
      (row.subject === null || row.subject === wanted) &&
      (!row.valid_until || (until !== null && row.valid_until >= until)),
  );
  if (open)
    return refuse(
      `It is open already, ${open.valid_until ? `until ${open.valid_until}` : "with no end"} (entitlement #${open.id}): extend that one instead.`,
      "subject",
    );
  return {
    ok: true,
    apply: () => {
      world.course.entitlements.unshift({
        id: ++world.seq,
        user: account,
        subject: wanted,
        source: "grant",
        reference: "",
        valid_until: until,
        note: reason,
        revoked_at: null,
        created: now(),
        modified: now(),
        history: [versionOf(now(), context.who.id, "+", reason, {})],
      });
    },
  };
}

function extendRule(context: Context, entitlement: Entitlement | undefined, days: unknown, reason: string): Outcome {
  if (!entitlement) return refuse("No such entitlement (or not one you may change).", "target");
  if (entitlement.revoked_at) return refuse("It was revoked: grant access again instead.");
  if (!entitlement.valid_until) return refuse("It has no end date: nothing to extend.");
  if (typeof days !== "number" || !Number.isInteger(days) || days < 1 || days > 365)
    return refuse("From 1 to 365 days.", "days");
  return {
    ok: true,
    apply: () => {
      const from = Math.max(Date.parse(entitlement.valid_until!), Date.parse(day(Date.now())));
      const until = day(from + days * DAY);
      entitlement.history.unshift(
        versionOf(now(), context.who.id, "~", reason, { valid_until: [entitlement.valid_until, until] }),
      );
      entitlement.valid_until = until;
      entitlement.modified = now();
    },
  };
}

function revokeRule(context: Context, entitlement: Entitlement | undefined, reason: string): Outcome {
  if (!entitlement) return refuse("No such entitlement (or not one you may change).", "target");
  if (entitlement.revoked_at) return refuse("It was revoked already.");
  if (stateOf(entitlement) === "ended") return refuse(`It ended on ${entitlement.valid_until}: nothing to revoke.`);
  return {
    ok: true,
    apply: () => {
      const yesterday = day(Date.now() - DAY);
      entitlement.history.unshift(
        versionOf(now(), context.who.id, "~", reason, { valid_until: [entitlement.valid_until, yesterday] }),
      );
      entitlement.valid_until = yesterday;
      entitlement.revoked_at = now();
      entitlement.modified = now();
    },
  };
}

const LEVELS = {
  difficulty: ["easy", "medium", "hard"],
  bloom: ["remember", "understand", "apply", "analyse", "evaluate", "create"],
};

function metadataRule(context: Context, item: Item | undefined, payload: Body): Outcome {
  if (!item || item.deleted_at) return refuse("No such quiz item (or not one you may change).", "target");
  const changes: Partial<Item> = {};
  if ("topic" in payload) {
    if (text(payload.topic).length > 120) return refuse("At most 120 characters.", "topic");
    changes.topic = text(payload.topic);
  }
  if ("marks" in payload) {
    const marks = payload.marks;
    if (typeof marks !== "number" || !Number.isInteger(marks) || marks < 1 || marks > 10)
      return refuse("A whole number from 1 to 10.", "marks");
    changes.marks = marks;
  }
  for (const name of ["difficulty", "bloom"] as const) {
    if (!(name in payload)) continue;
    const value = text(payload[name]);
    if (value && !LEVELS[name].includes(value))
      return refuse(`One of ${LEVELS[name].join(", ")}, or empty (not set).`, name);
    (changes as Body)[name] = value;
  }
  const add = Array.isArray(payload.tags_add) ? payload.tags_add.map(text).filter(Boolean) : [];
  const remove = Array.isArray(payload.tags_remove) ? payload.tags_remove.map(text).filter(Boolean) : [];
  if (!Object.keys(changes).length && !add.length && !remove.length)
    return refuse("Say what to change: topic, marks, difficulty, bloom, tags_add or tags_remove.");
  return {
    ok: true,
    apply: () => {
      const before: Body = {};
      for (const [name, value] of Object.entries(changes)) {
        before[name] = [(item as Body)[name], value];
        (item as Body)[name] = value;
      }
      item.tags = [...new Set([...item.tags.filter((tag) => !remove.includes(tag)), ...add])].sort();
      item.history.unshift(versionOf(now(), context.who.id, "~", "the quiz bank", before));
    },
  };
}

// ---- The routes ----

const findId = <T extends { id: number }>(rows: T[], id: string | undefined) =>
  rows.find((row) => String(row.id) === id);

function rowsOf(world: CourseWorld, kind: string): (Clip | Card | Item)[] {
  return kind === "clips" ? world.clips : kind === "cards" ? world.cards : world.items;
}

function siblingsOf(world: CourseWorld, kind: string, row: Clip | Card | Item): (Clip | Card | Item)[] {
  if (kind === "clips") return byOrder(live(world.clips.filter((clip) => clip.revision === (row as Clip).revision)));
  const all = kind === "cards" ? world.cards : world.items;
  return byOrder(live(all.filter((each) => (each as Card).chapter === (row as Card).chapter)));
}

const NOUN: Record<string, [string, string]> = {
  clips: ["clip", "revision"],
  cards: ["card", "chapter"],
  items: ["quiz item", "chapter"],
};

function move(context: Context, kit: Kit, kind: string, row: Clip | Card | Item): Response {
  const body = context.body;
  const to = text(body.to);
  const [noun, parent] = NOUN[kind];
  if (!["first", "last", "before", "after"].includes(to))
    return kit.invalid(refusal("One of first, last, before, after.", "to"));
  if (row.deleted_at) return kit.invalid(refusal(`This ${noun} is in the bin: restore it first.`));
  const siblings = siblingsOf(context.world.course, kind, row);
  const rest = siblings.filter((each) => each.id !== row.id);
  let index = to === "first" ? 0 : rest.length;
  if (to === "before" || to === "after") {
    const target = body.target === null || body.target === undefined ? "" : String(body.target);
    if (!target || target === String(row.id))
      return kit.invalid(refusal(`Another ${noun} of the same ${parent} to move it ${to}.`, "target"));
    const at = rest.findIndex((each) => String(each.id) === target);
    if (at < 0) return kit.invalid(refusal(`Not a ${noun} of the same ${parent} (or it is in the bin).`, "target"));
    index = at + (to === "after" ? 1 : 0);
  }
  rest.splice(index, 0, row);
  const before = row.order;
  rest.forEach((each, position) => {
    each.order = position + 1;
  });
  kit.record(context, "course.moved", {
    target_type: `learn.${MODELS[kind]}`,
    target_id: String(row.id),
    target_label: `${noun[0].toUpperCase()}${noun.slice(1)} #${row.id}`,
    changes: { order: [before, row.order] },
    details: { to, target: body.target ?? null },
  });
  return kit.json(
    200,
    kind === "clips" ? clipOut(context.world.course, row as Clip) : { id: row.id, order: row.order },
  );
}

function rowRoute(context: Context, kit: Kit, kind: string): Response {
  const { method, parts, body, world } = context;
  const [, , id, verb, extra] = parts;
  const course = world.course;
  const row = findId(rowsOf(course, kind), id) as Clip | Card | Item | undefined;
  if (kind === "items" && !id && method === "GET") return itemsList(context, kit);
  if (!row || extra) return kit.notFound();
  const target = {
    target_type: `learn.${MODELS[kind]}`,
    target_id: String(row.id),
    target_label: `${NOUN[kind][0]} #${row.id}`,
  };
  const out = () =>
    kind === "clips"
      ? clipOut(course, row as Clip)
      : kind === "items"
        ? itemOut(course, row as Item)
        : { ...(row as Card), bin_until: binUntil(row.deleted_at) };
  if (!verb && method === "GET") return kit.json(200, out());
  if (verb === "history" && kind === "items" && method === "GET") return kit.json(200, (row as Item).history);
  if (!verb && method === "PATCH") {
    if (row.deleted_at) return kit.notFound();
    const editable =
      kind === "clips"
        ? ["title", "kind", "notes", "is_free_preview", "tags"]
        : kind === "cards"
          ? ["front", "back", "tags"]
          : ["kind", "text", "options", "answer", "explanation", "topic", "marks", "difficulty", "bloom", "tags"];
    const changes: Body = {};
    for (const name of editable) {
      if (!(name in body)) continue;
      const value = body[name];
      if ((name === "title" || name === "front" || name === "text") && !text(value))
        return kit.invalid(refusal("This field may not be blank.", name));
      if (name === "marks" && (typeof value !== "number" || value < 1 || value > 10))
        return kit.invalid(refusal("Ensure this value is less than or equal to 10.", name));
      if (name === "answer" && kind === "items" && (row as Item).kind === "mcq" && !/^\d+$/.test(text(value)))
        return kit.invalid(refusal("The right option's number: 1 for the first.", name));
      changes[name] = [(row as Body)[name], value];
      (row as Body)[name] = value;
    }
    if (kind === "items") (row as Item).history.unshift(versionOf(now(), context.who.id, "~", "the console", changes));
    kit.record(context, `course.${kind === "items" ? "item" : MODELS[kind]}_changed`, { ...target, changes });
    return kit.json(200, out());
  }
  if (!verb && method === "DELETE") {
    if (row.deleted_at) return kit.notFound();
    row.deleted_at = now();
    kit.record(context, "course.deleted", target);
    return kit.json(200, binRow(course, kind as S["CourseRowKindEnum"], row));
  }
  if (method !== "POST") return kit.notFound();
  if (verb === "move") return move(context, kit, kind, row);
  if (verb === "restore") {
    if (!row.deleted_at) return kit.invalid(refusal(`This ${NOUN[kind][0]} is not in the bin.`));
    if (Date.parse(row.deleted_at) < Date.now() - BIN_DAYS * DAY)
      return kit.invalid(refusal(`It was in the bin more than ${BIN_DAYS} days: it goes with the next purge.`));
    row.deleted_at = null;
    const siblings = siblingsOf(course, kind, row);
    const [moved] = siblings.splice(
      siblings.findIndex((each) => each.id === row.id),
      1,
    );
    siblings.splice(Math.min(moved.order - 1, siblings.length), 0, moved);
    siblings.forEach((each, position) => {
      each.order = position + 1;
    });
    kit.record(context, "course.restored", target);
    return kit.json(200, out());
  }
  if (verb === "retry" && kind === "clips") {
    const clip = row as Clip;
    if (!clip.has_video || clip.deleted_at || !(clip.processing === "failed" || clip.stuck))
      return kit.invalid(refusal("Only a failed clip, or one stuck processing, is processed again."));
    Object.assign(clip, {
      processing: "uploaded",
      reason: "",
      error_detail: "",
      stuck: false,
      processing_since: now(),
    });
    kit.record(context, "course.clip_retried", target);
    return kit.json(200, clipOut(course, clip));
  }
  if (verb === "flag" && kind === "items") {
    const item = row as Item;
    const created = item.flagged === null;
    if (created) item.flagged = ++world.seq;
    if (created) kit.record(context, "course.item_flagged", { ...target, details: { report: item.flagged } });
    return kit.json(created ? 201 : 200, { report: item.flagged, created });
  }
  return kit.notFound();
}

function itemsList(context: Context, kit: Kit): Response {
  const course = context.world.course;
  const query = (name: string) => context.url.searchParams.get(name) ?? "";
  const rows = live(course.items)
    .filter((item) => {
      const chapter = chapterOf(course, item.chapter);
      const flags = item.stats.n_too_small ? [] : item.stats.flags;
      if (query("subject") && subjectCode(course, chapter) !== query("subject").toUpperCase()) return false;
      if (query("chapter") && String(item.chapter) !== query("chapter")) return false;
      if (query("kind") && item.kind !== query("kind")) return false;
      for (const level of ["difficulty", "bloom"] as const)
        if (query(level) && item[level] !== (query(level) === "none" ? "" : query(level))) return false;
      if (query("source") === "book" && !item.source) return false;
      if (query("source") === "app" && item.source) return false;
      if (query("flags") === "any" && !flags.length) return false;
      if (query("flags") && query("flags") !== "any" && !flags.some((flag) => flag.startsWith(query("flags"))))
        return false;
      if (query("flagged") && (item.flagged !== null) !== (query("flagged") === "true")) return false;
      if (query("q") && !item.text.toLowerCase().includes(query("q").toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => a.chapter - b.chapter || a.order - b.order || a.id - b.id)
    .map((item) => itemRow(course, item));
  return kit.paginate(context, rows);
}

function revisionRoute(context: Context, kit: Kit): Response {
  const { method, parts, body, world, who } = context;
  const [, , id, verb, extra] = parts;
  const course = world.course;
  const revision = findId(course.revisions, id);
  if (!revision || extra) return kit.notFound();
  const can = (perm: string) => context.permissions.includes(perm);
  const answer = () => kit.json(200, revisionOut(course, revision, who.id, can));
  const target = { target_type: "learn.revision", target_id: String(revision.id), target_label: revision.title };
  if (!verb && method === "GET") return answer();
  if (!verb && method === "PATCH") {
    if ("title" in body && !text(body.title)) return kit.invalid(refusal("This field may not be blank.", "title"));
    if ("target_minutes" in body) {
      const minutes = body.target_minutes;
      if (typeof minutes !== "number" || !Number.isInteger(minutes) || minutes < 1 || minutes > 60)
        return kit.invalid(refusal("From 1 to 60 minutes.", "target_minutes"));
      revision.target_minutes = minutes;
    }
    if ("title" in body) revision.title = text(body.title);
    revision.modified = now();
    kit.record(context, "course.revision_changed", target);
    return answer();
  }
  if (method !== "POST") return kit.notFound();
  const own = revision.submitted_by === who.id;
  const status = STATUS_LABEL[revision.status];
  if (verb !== "submit" && verb !== "unpublish" && own)
    return kit.json(403, {
      detail: "You submitted this revision: another reviewer decides it.",
      code: "own_edit",
    });
  const comment = text(body.comment);
  switch (verb) {
    case "submit":
      if (revision.status !== "draft")
        return kit.invalid(refusal(`It is ${status}: only a draft is submitted for review.`));
      Object.assign(revision, { status: "review", submitted_by: who.id, submitted_at: now(), reviewer: null });
      kit.record(context, "course.revision_submitted", target);
      return answer();
    case "approve":
      if (revision.status !== "review")
        return kit.invalid(refusal(`It is ${status}: only a revision in review is approved.`));
      Object.assign(revision, { status: "approved", reviewer: who.id });
      kit.record(context, "course.revision_approved", { ...target, reason: comment });
      return answer();
    case "needs-changes":
      if (!comment) return kit.invalid(refusal("Say what to change.", "comment"));
      if (revision.status !== "review")
        return kit.invalid(refusal(`It is ${status}: only a revision in review is sent back.`));
      Object.assign(revision, { status: "draft", reviewer: null, publish_at: null });
      kit.record(context, "course.revision_needs_changes", { ...target, reason: comment });
      return answer();
    case "publish": {
      const at = body.publish_at ? String(body.publish_at) : null;
      if (at !== null && (Number.isNaN(Date.parse(at)) || Date.parse(at) <= Date.now()))
        return kit.invalid(refusal("A time to come, or none to publish it now.", "publish_at"));
      if (at !== null && Date.parse(at) > Date.now() + 366 * DAY)
        return kit.invalid(refusal("Within a year.", "publish_at"));
      if (revision.status === "published") return kit.invalid(refusal("It is published already."));
      if (revision.status === "draft") return kit.invalid(refusal("It is a draft: submit it for review first."));
      if (!at && !live(course.clips).some((clip) => clip.revision === revision.id && clip.processing === "ready"))
        return kit.invalid(refusal("None of its clips is ready yet: it would publish nothing to watch."));
      if (revision.status === "review") revision.reviewer = who.id;
      Object.assign(revision, at ? { status: "approved", publish_at: at } : { status: "published", publish_at: null });
      kit.record(context, at ? "course.revision_scheduled" : "course.revision_published", {
        ...target,
        details: at ? { publish_at: at } : {},
      });
      return answer();
    }
    case "unpublish":
      if (revision.status === "draft") return kit.invalid(refusal("It is a draft already."));
      Object.assign(revision, { status: "draft", reviewer: null, publish_at: null });
      kit.record(context, "course.revision_unpublished", target);
      return answer();
  }
  return kit.notFound();
}

function entitlementRoute(context: Context, kit: Kit): Response {
  const { method, parts, body, world, url } = context;
  const [, , id, verb, extra] = parts;
  const course = world.course;
  if (extra) return kit.notFound();
  if (!id && method === "GET") {
    const query = (name: string) => url.searchParams.get(name) ?? "";
    const email = query("q").toLowerCase();
    let rows = [...course.entitlements].sort((a, b) => b.created.localeCompare(a.created) || b.id - a.id);
    if (email) {
      const learner = course.learners.find((each) => each.email === email);
      rows = rows.filter((row) => row.user === learner?.id);
      kit.record(context, "customer.lookup", {
        details: { query_hash: `h${email.length}${email.charCodeAt(0)}`, found: rows.length },
      });
    }
    const subject = query("subject").toUpperCase();
    const out = rows
      .filter(
        (row) =>
          (!subject || (subject === "ALL" ? row.subject === null : row.subject === subject)) &&
          (!query("source") || row.source === query("source")) &&
          (!query("state") || stateOf(row) === query("state")),
      )
      .map((row) => entitlementOut(context, row));
    return kit.paginate(context, out);
  }
  if (!id && method === "POST") {
    const reason = text(body.reason);
    if (!reason) return kit.invalid(refusal("Say why.", "reason"));
    const account = Number(body.user);
    const rule = grantRule(
      context,
      account,
      text(body.subject),
      body.valid_until ? String(body.valid_until) : null,
      reason,
    );
    if (!rule.ok) return kit.invalid(rule.fields);
    rule.apply();
    const made = course.entitlements[0];
    made.reference = text(body.reference).slice(0, 40);
    kit.record(context, "course.entitlement_granted", {
      target_type: "learn.entitlement",
      target_id: String(made.id),
      target_label: `Entitlement #${made.id}`,
      reason,
    });
    return kit.json(201, entitlementOut(context, made));
  }
  const entitlement = findId(course.entitlements, id);
  if (!entitlement) return kit.notFound();
  const target = {
    target_type: "learn.entitlement",
    target_id: String(entitlement.id),
    target_label: `Entitlement #${entitlement.id}`,
  };
  if (!verb && method === "GET")
    return kit.json(200, { ...entitlementOut(context, entitlement), history: entitlement.history });
  if (method !== "POST") return kit.notFound();
  const reason = text(body.reason);
  if (!reason) return kit.invalid(refusal("Say why.", "reason"));
  const rule =
    verb === "extend"
      ? extendRule(context, entitlement, body.days, reason)
      : verb === "revoke"
        ? revokeRule(context, entitlement, reason)
        : null;
  if (!rule) return kit.notFound();
  if (!rule.ok) return kit.invalid(rule.fields);
  rule.apply();
  kit.record(context, `course.entitlement_${verb === "extend" ? "extended" : "revoked"}`, { ...target, reason });
  return kit.json(200, entitlementOut(context, entitlement));
}

function lookup(context: Context, kit: Kit): Response {
  const course = context.world.course;
  const typed = text(context.body.code)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
  if (!typed) return kit.invalid(refusal("This field may not be blank.", "code"));
  const code = course.codes.find((each) => each.code.replace(/-/g, "") === typed);
  const answer: S["CourseCodeLookup"] = {
    state: "unknown",
    line: "No such code: check it against the one printed in the book (a code has no 0, O, 1 or I).",
    batch: null,
    batch_state: null,
    subject: null,
    redeemed_at: null,
    voided_at: null,
    redeemed_by: null,
  };
  if (code) {
    const batch = course.batches.find((each) => each.label === code.batch);
    const subject = code.subject ? SUBJECT_NAMES[code.subject] : "every subject";
    Object.assign(answer, {
      batch: code.batch,
      subject,
      batch_state: batch ? batchState(context, batch) : null,
    });
    if (code.voided_at) {
      Object.assign(answer, { state: "void", voided_at: code.voided_at });
      answer.line = `Void since ${code.voided_at.slice(0, 10)}${batch?.void_reason ? ` (${batch.void_reason})` : ""}: batch ${code.batch} (${subject}). It opens nothing.`;
    } else if (code.redeemed_at && code.redeemed_by) {
      const learner = course.learners.find((each) => each.id === code.redeemed_by);
      Object.assign(answer, {
        state: "redeemed",
        redeemed_at: code.redeemed_at,
        redeemed_by: {
          id: code.redeemed_by,
          email: mask(learner?.email ?? "someone@example.com"),
          is_minor: Boolean(learner?.is_minor),
        },
      });
      answer.line = `Redeemed on ${code.redeemed_at.slice(0, 10)} by account #${code.redeemed_by}: batch ${code.batch} (${subject}).`;
      kit.record(context, "sensitive_read", {
        target_type: "accounts.user",
        target_id: String(code.redeemed_by),
        target_label: `Account #${code.redeemed_by}`,
        details: { what: "book_code", child: Boolean(learner?.is_minor) },
      });
    } else {
      answer.state = "unused";
      answer.line = `Not redeemed yet: batch ${code.batch} (${subject}).${batch && !batch.dispatched_at ? " Its batch is not marked dispatched yet." : ""}`;
    }
  }
  kit.record(context, "course.code_lookup", { details: { state: answer.state, code_hash: `h${typed.length}` } });
  return kit.json(200, answer);
}

function codesRoute(context: Context, kit: Kit): Response {
  const { method, parts, body, world, who, url } = context;
  const [, , part, key, verb, extra] = parts;
  const course = world.course;
  if (part === "lookup" && method === "POST" && !key) return lookup(context, kit);
  if (part === "void" && method === "POST" && !key) {
    const typed = text(body.code)
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    const reason = text(body.reason);
    if (!reason) return kit.invalid(refusal("Say why.", "reason"));
    const code = course.codes.find((each) => each.code.replace(/-/g, "") === typed);
    if (!code) return kit.invalid(refusal("No such code.", "code"));
    if (code.redeemed_at) return kit.invalid(refusal("It was redeemed: revoke the access it opened instead.", "code"));
    if (code.voided_at) return kit.invalid(refusal("It is void already.", "code"));
    code.voided_at = now();
    const batch = course.batches.find((each) => each.label === code.batch);
    if (batch) batch.void += 1;
    kit.record(context, "course.code_voided", { reason, details: { code_hash: `h${typed.length}` } });
    return kit.json(200, { id: course.codes.indexOf(code) + 1, batch: code.batch, voided_at: code.voided_at });
  }
  if (part === "report" && method === "GET" && !key) {
    const batches = [...course.batches].sort((a, b) => b.created.localeCompare(a.created));
    const rows = batches.map((batch) => ({
      batch: batchOut(context, batch),
      printed: batch.printed,
      sold: batch.product ? batch.sold : null,
      activated: batch.redeemed,
      revoked: batch.revoked,
      void: batch.void,
      activation_rate: batch.printed ? batch.redeemed / batch.printed : null,
      districts: batch.districts,
    }));
    const sum = (name: "printed" | "activated" | "revoked" | "void") =>
      rows.reduce((total, row) => total + row[name], 0);
    const printed = sum("printed");
    return kit.json(200, {
      computed_at: now(),
      min_cell: MIN_CELL,
      definitions: {
        printed: "Codes made for the print run.",
        sold: "Copies of its book sold on the website from the day its codes were made until the next print run.",
        activated: "Codes redeemed in the app.",
        revoked: "Access a code opened that staff took back.",
        void: "Codes voided: they open nothing.",
        activation_rate: "Activated ÷ printed.",
        districts: "Where codes were redeemed, a district with fewer than 10 hidden.",
      },
      totals: {
        printed,
        sold: rows.reduce((total, row) => total + (row.sold ?? 0), 0),
        activated: sum("activated"),
        revoked: sum("revoked"),
        void: sum("void"),
        activation_rate: printed ? sum("activated") / printed : null,
      },
      rows,
    } satisfies S["CourseReport"]);
  }
  if (part !== "batches") return kit.notFound();
  if (!key && method === "GET") {
    const query = (name: string) => url.searchParams.get(name) ?? "";
    const subject = query("subject").toUpperCase();
    const rows = [...course.batches]
      .sort((a, b) => b.created.localeCompare(a.created) || b.id - a.id)
      .map((batch) => batchOut(context, batch))
      .filter(
        (batch) =>
          (!subject || (subject === "ALL" ? batch.subject === null : batch.subject === subject)) &&
          (!query("state") || batch.state === query("state")) &&
          (!query("q") || batch.label.toLowerCase().includes(query("q").toLowerCase())),
      );
    return kit.paginate(context, rows);
  }
  if (!key && method === "POST") return makeBatch(context, kit);
  const batch = course.batches.find((each) => batchKey(each) === key || `~${each.id}` === key);
  if (!batch || extra) return kit.notFound();
  const target = {
    target_type: "learn.codebatch",
    target_id: String(batch.id),
    target_label: `Code batch ${batch.label}`,
  };
  if (!verb && method === "GET") {
    const out = batchOut(context, batch);
    const job = world.jobs.find((each) => each.id === batch.job);
    const until = job?.state === "done" && job.finished_at ? Date.parse(job.finished_at) + DAY : null;
    const fileUntil = until && until > Date.now() && job?.started_by === who.id ? new Date(until).toISOString() : null;
    return kit.json(200, {
      ...out,
      redeemed_by_week: batch.weeks,
      signals: batch.signals,
      activation_rate: batch.codes ? batch.redeemed / batch.codes : null,
      file_until: fileUntil,
      generation: job ? kit.visibleJob(context, job) : null,
    } satisfies S["CourseBatchDetail"]);
  }
  if (method !== "POST") return kit.notFound();
  const state = batchState(context, batch);
  if (verb === "dispatched") {
    if (state !== "ready")
      return kit.invalid(refusal(`It is ${state}: only a print run whose codes are made, not yet dispatched.`));
    const at = body.at ? String(body.at) : now();
    if (Number.isNaN(Date.parse(at)) || Date.parse(at) > Date.now() + 60_000)
      return kit.invalid(refusal("When the books left: now or before.", "at"));
    batch.dispatched_at = at;
    kit.record(context, "course.batch_dispatched", { ...target, details: { at } });
    return kit.json(200, batchOut(context, batch));
  }
  if (verb === "void") {
    const reason = text(body.reason);
    if (!reason) return kit.invalid(refusal("Say why.", "reason"));
    if (state === "void") return kit.invalid(refusal("It is void already."));
    let voided = 0;
    for (const code of course.codes)
      if (code.batch === batch.label && !code.redeemed_at && !code.voided_at) {
        code.voided_at = now();
        voided += 1;
      }
    voided = Math.max(voided, batch.codes - batch.redeemed - batch.void);
    batch.void += voided;
    batch.voided_at = now();
    batch.void_reason = reason;
    kit.record(context, "course.batch_voided", { ...target, reason, details: { voided } });
    return kit.json(200, { batch: batchOut(context, batch), voided });
  }
  return kit.notFound();
}

function makeBatch(context: Context, kit: Kit): Response {
  const { body, world, who } = context;
  const course = world.course;
  const label = text(body.label);
  if (!LABEL.test(label))
    return kit.invalid(refusal("Letters, digits and hyphens, 40 at most, starting with a letter or digit.", "label"));
  if (course.batches.some((batch) => batch.label.toLowerCase() === label.toLowerCase()))
    return kit.invalid(refusal("A print run has this label already: give the new one its own (PHY-2027-2).", "label"));
  const subject = text(body.subject).toUpperCase();
  if (subject !== "ALL" && !SUBJECT_NAMES[subject])
    return kit.invalid(refusal(`No subject ${subject || "given"}: PHY, CHE, MAT, BIO or ALL.`, "subject"));
  const count = body.count;
  if (typeof count !== "number" || !Number.isInteger(count) || count < 1 || count > 100_000)
    return kit.invalid(refusal("From 1 to 100,000 codes at a time.", "count"));
  const index = world.orders.products.findIndex((each) => each.slug === text(body.product));
  const book = world.orders.products[index];
  if (!book || book.kind === "digital") return kit.invalid(refusal("A book (printed) the codes go into.", "product"));
  const id = ++world.seq;
  const job = kit.startJob(context, "code_batch", { batch: id, label, count }, Array.from({ length: count }, String));
  job._result = { batch: label, codes: count };
  const batch: Batch = {
    id,
    label,
    subject: subject === "ALL" ? null : subject,
    product: { id: 2100 + index, slug: book.slug, title: book.title },
    printed: count,
    codes: 0,
    redeemed: 0,
    void: 0,
    revoked: 0,
    sold: 0,
    note: text(body.note),
    created: now(),
    generated_at: null,
    generated_by: who.id,
    dispatched_at: null,
    voided_at: null,
    void_reason: "",
    job: job.id,
    weeks: [],
    signals: [],
    districts: [],
  };
  course.batches.unshift(batch);
  kit.record(context, "course.batch_requested", {
    target_type: "learn.codebatch",
    target_id: String(id),
    target_label: `Code batch ${label}`,
    details: { count, subject: subject.toLowerCase(), job: job.id },
  });
  return kit.json(202, { batch: batchOut(context, batch), job: kit.visibleJob(context, job) });
}

function learnerRoute(context: Context, kit: Kit): Response {
  const { method, parts, world } = context;
  const [, , id, part, device, verb, extra] = parts;
  const course = world.course;
  const known = course.learners.find((each) => String(each.id) === id);
  const user = world.users.find((each) => String(each.id) === id);
  if ((!known && !user) || extra) return kit.notFound();
  const learner: Learner = known ?? {
    id: Number(id),
    name: user?.full_name ?? "",
    email: user?.email ?? "",
    is_minor: Boolean(user?.under_18),
    is_active: user?.status !== "suspended",
    adult: !user?.under_18,
    summary: {
      clips_watched: 0,
      minutes_watched: 0,
      quiz_answers: 0,
      quiz_accuracy: null,
      card_reviews: 0,
      last_active: null,
      last_active_week: null,
    },
    chapters: [],
    devices: [],
    tickets: [],
  };
  const target = {
    target_type: "accounts.user",
    target_id: String(learner.id),
    target_label: `Account #${learner.id}`,
  };
  if (!part && method === "GET") {
    kit.record(context, "sensitive_read", { ...target, details: { what: "learner", child: learner.is_minor } });
    const can = (perm: string) => context.permissions.includes(perm);
    return kit.json(200, {
      logged: true,
      user: {
        id: learner.id,
        name: learner.name,
        email: mask(learner.email),
        is_minor: learner.is_minor,
        is_active: learner.is_active,
      },
      summary_only: !learner.adult,
      summary: learner.summary,
      entitlements: course.entitlements
        .filter((row) => row.user === learner.id)
        .sort((a, b) => b.created.localeCompare(a.created))
        .map((row) => entitlementOut(context, row)),
      codes: can("learn.view_bookcode")
        ? course.codes
            .filter((code) => code.redeemed_by === learner.id && code.redeemed_at)
            .map((code, index) => ({
              id: index + 1,
              batch: code.batch,
              subject: code.subject ?? "ALL",
              redeemed_at: code.redeemed_at!,
            }))
        : null,
      devices: learner.devices,
      chapters: learner.chapters,
      tickets: can("support.view_ticket") ? learner.tickets : null,
    } satisfies S["CourseLearner"]);
  }
  if (part === "devices" && verb === "sign-out" && method === "POST") {
    const found = learner.devices.find((each) => String(each.id) === device);
    if (!found) return kit.notFound();
    learner.devices = learner.devices.filter((each) => each !== found);
    kit.record(context, "course.device_signed_out", {
      ...target,
      details: { device: found.id, platform: found.platform },
    });
    return kit.noContent();
  }
  return kit.notFound();
}

export function courseRoute(context: Context, kit: Kit): Response {
  const { method, parts, body, world, url } = context;
  const [, area, id, verb, extra] = parts;
  const course = world.course;
  switch (area) {
    case "subjects": {
      if (method !== "GET") return kit.notFound();
      if (!id)
        return kit.json(
          200,
          course.subjects.map((subject) => {
            const chapters = course.chapters.filter((chapter) => chapter.subject === subject.id);
            const ids = new Set(chapters.map((chapter) => chapter.id));
            const revisions = course.revisions.filter((revision) => ids.has(revision.chapter));
            const revisionIds = new Set(revisions.map((revision) => revision.id));
            const clips = live(course.clips.filter((clip) => revisionIds.has(clip.revision)));
            return {
              ...subject,
              chapters: chapters.length,
              published: revisions.filter((revision) => revision.status === "published").length,
              in_review: revisions.filter((revision) => revision.status === "review").length,
              scheduled: revisions.filter((revision) => revision.status === "approved" && revision.publish_at).length,
              clips: clips.length,
              failed: clips.filter((clip) => clip.processing === "failed").length,
              cards: live(course.cards.filter((card) => ids.has(card.chapter))).length,
              items: live(course.items.filter((item) => ids.has(item.chapter))).length,
              bin:
                course.clips.filter((clip) => revisionIds.has(clip.revision) && clip.deleted_at).length +
                course.cards.filter((card) => ids.has(card.chapter) && card.deleted_at).length +
                course.items.filter((item) => ids.has(item.chapter) && item.deleted_at).length,
            } satisfies S["CourseSubject"];
          }),
        );
      if (verb !== "outline" || extra) return kit.notFound();
      const found = outline(course, Number(id));
      return found ? kit.json(200, found) : kit.notFound();
    }
    case "chapters": {
      const chapter = findId(course.chapters, id);
      if (!chapter || verb) return kit.notFound();
      if (method === "PATCH") {
        if ("must_do" in body) chapter.must_do = String(body.must_do ?? "");
        kit.record(context, "course.chapter_changed", {
          target_type: "learn.chapter",
          target_id: String(chapter.id),
          target_label: `Chapter ${chapter.number}`,
        });
      }
      return kit.json(200, chapter);
    }
    case "revisions":
      return revisionRoute(context, kit);
    case "clips":
    case "cards":
    case "items":
      return rowRoute(context, kit, area);
    case "bin": {
      const kind = url.searchParams.get("kind") || "clips";
      if (!(kind in MODELS)) return kit.invalid(refusal("clips, cards or items.", "kind"));
      const rows = rowsOf(course, kind)
        .filter((row) => row.deleted_at)
        .sort((a, b) => (b.deleted_at ?? "").localeCompare(a.deleted_at ?? ""))
        .map((row) => binRow(course, kind as S["CourseRowKindEnum"], row));
      return kit.paginate(context, rows);
    }
    case "entitlements":
      return entitlementRoute(context, kit);
    case "codes":
      return codesRoute(context, kit);
    case "learners":
      return learnerRoute(context, kit);
  }
  return kit.notFound();
}

/** POST jobs/ with kind bulk_action naming a course action: each row through its rule; a dry run changes nothing;
 *  above the person's bulk_rows the job waits for an approver (its change request). */
export function startCourseBulk(context: Context, kit: Kit): Response {
  const { body, world } = context;
  const params = (body.params ?? {}) as Body;
  const action = text(params.action);
  const targets = Array.isArray(params.targets) ? params.targets : [];
  const payload = (params.payload ?? {}) as Body;
  const reason = text(params.reason);
  const dry = body.dry_run === true;
  if (!targets.length) return kit.invalid({ params: { targets: ["At least one row."] } });
  if (!reason) return kit.invalid({ params: { reason: ["Say why: it is kept with each change."] } });
  const course = world.course;
  const outcomes: Record<string, number> = {};
  const errors: S["Job"]["errors"] = [];
  const applies: (() => void)[] = [];
  for (const target of targets) {
    const key = String(target);
    const rule =
      action === "item_metadata"
        ? metadataRule(context, findId(course.items, key), payload)
        : action === "entitlement.grant"
          ? grantRule(
              context,
              Number(key),
              text(payload.subject),
              payload.valid_until ? String(payload.valid_until) : null,
              reason,
            )
          : action === "entitlement.extend"
            ? extendRule(context, findId(course.entitlements, key), payload.days, reason)
            : revokeRule(context, findId(course.entitlements, key), reason);
    if (!rule.ok) {
      outcomes.refused = (outcomes.refused ?? 0) + 1;
      errors.push({ id: key, label: key, message: Object.values(rule.fields).flat().join(" ") });
      continue;
    }
    outcomes[dry ? "valid" : "executed"] = (outcomes[dry ? "valid" : "executed"] ?? 0) + 1;
    applies.push(rule.apply);
  }
  const job: MockJob = kit.startJob(context, "bulk_action", { action, targets, payload, reason }, targets.map(String));
  job.dry_run = dry;
  job.errors = errors;
  job._result = { outcomes, waiting: [] };
  const limit = kit.limitOf(context, "bulk_rows");
  if (!dry && limit !== null && targets.length > limit) {
    kit.waiting(context, {
      action: "job.run",
      label: "Run a large job",
      target_type: "staff.job",
      target_id: String(job.id),
      target_label: `Job #${job.id}`,
      payload: { job: job.id, kind: "bulk_action", total: targets.length, params: { action } },
      amount: null,
      reason: `Bulk action of ${targets.length} rows (job #${job.id})`,
      rule: `${targets.length} rows are above the limit of ${limit}.`,
      checker: "staff.approve_export",
    });
    job.state = "queued";
    job.change_request_id = world.changeRequests[0].id;
    return kit.json(202, kit.visibleJob(context, job));
  }
  if (!dry) applies.forEach((apply) => apply());
  return kit.json(202, kit.visibleJob(context, job));
}

/** POST jobs/ with kind code_batch: a print run whose first job failed, made again. */
export function remakeBatchJob(context: Context, kit: Kit): Response {
  const params = (context.body.params ?? {}) as Body;
  if (context.body.dry_run === true) return kit.invalid({ dry_run: ["Making book codes has no dry run."] });
  const batch = context.world.course.batches.find((each) => each.id === params.batch);
  if (!batch) return kit.invalid({ params: { batch: ["A batch made from course/codes/batches/."] } });
  const state = batchState(context, batch);
  if (state !== "failed") return kit.invalid({ params: { batch: [`It is ${state}: nothing to make again.`] } });
  const job = kit.startJob(
    context,
    "code_batch",
    { batch: batch.id, label: batch.label, count: batch.printed },
    Array.from({ length: batch.printed }, String),
  );
  job._result = { batch: batch.label, codes: batch.printed };
  batch.job = job.id;
  return kit.json(202, kit.visibleJob(context, job));
}

/** A done code_batch job's file, for its starter: the codes once (the mock's are made up, never the fixtures'). */
export function codeBatchFile(job: MockJob): Response {
  const params = job.params as Body;
  const label = text(params.label);
  const letters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const code = (index: number) =>
    Array.from({ length: 12 }, (_, at) => letters[(index * 7 + at * 13 + at * index) % letters.length])
      .join("")
      .replace(/(.{4})(?=.)/g, "$1-");
  const rows = Array.from({ length: Math.min(job.total, 5000) }, (_, index) => `${code(index + 1)},${label},`);
  return new Response(["code,batch,subject", ...rows].join("\n") + "\n", {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="${label}-book-codes.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
