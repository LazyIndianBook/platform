#!/usr/bin/env node
// ExamLeaf atlas, part 1: full-page captures of every page of the Next.js frontend and of the Django admin, at 1280 px
// (desktop) and 390 px (phone), signed out, signed in as a student and as staff, in every state worth a picture: gated
// and open, empty and full, an error, Django away, no connection. Part 2 is build.py (the PDF). seed.py makes the
// temporary accounts and the rows the pages need (it runs inside `manage.py shell`; this script calls it).
//
//   node capture.mjs --repo <checkout> --out <dir> --env <backend env file> --fresh
//   node capture.mjs ... --only '<regex of scene ids>'   run some scenes again; their pictures replace the old ones
//   node capture.mjs ... --list                          the scenes, in order
//   node capture.mjs ... --only '^cleanup$' --cleanup    delete the temporary accounts (emails "atlas-...") and what they made
//   <checkout>/examleaf-web/.venv/bin/python build.py --manifest <dir>/manifest.json --repo <checkout> --out atlas.pdf
//
// It needs (README of examleaf-web, "Set up and run"; README of examleaf-frontend, "Environment"):
//   * <checkout>/examleaf-web/.venv and <checkout>/examleaf-frontend/node_modules (a copy-on-write copy of the main
//     checkout's, `cp -cR`: Turbopack refuses a symlink that leaves the project), Playwright with its Chromium;
//   * the frontend BUILT for the address it will be served at: NEXT_PUBLIC_SITE_URL=<--base> npm run build (production);
//   * the backend's environment in a file of `export NAME=value` lines (--env), as a production-like local run needs:
//       SITE_URL=<base> CSRF_TRUSTED_ORIGINS=<base> USE_X_FORWARDED_HOST=1 DEBUG=0 SECRET_KEY=<50+ random characters>
//       ALLOWED_HOSTS=localhost,127.0.0.1 SECURE_SSL_REDIRECT=0 (plain http on localhost) LEARN_CODE_SECRET=<anything>
//       EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend DATABASE_URL=sqlite:////abs/path/db.sqlite3?transaction_mode=IMMEDIATE&timeout=20
//       SUPPORT_EMAIL=<address> SELLER_ADDRESS=<..> SELLER_EMAIL=<..> SELLER_PHONE=<..> (invoices of live-mode orders need them)
//       API_THROTTLE_ANON=100000/minute API_THROTTLE_USER=100000/minute API_THROTTLE_AUTH=100000/minute API_THROTTLE_ORDER_LOOKUP=100000/hour
//     (a capture run makes hundreds of requests from one address: the defaults would answer 429)
//   * --fresh makes that database from nothing: migrate, bootstrap_roles, import_papers --all --fixtures,
//     import_chapter_insights --fixtures, build_quiz_items, seed_shop --stock 100, collectstatic.
// The script starts and restarts both servers itself (BASE's port for the frontend, --django-port, 8108, for Django:
// Django's page cache is per process and Next's data cache is on disk, so a change of data needs both restarted), logs
// in through the real pages (the staff user with the TOTP code computed from the secret of its device), takes the
// pictures and writes <out>/manifest.json: for every capture its area, route, state, viewport, page title, status
// and file, and the failures.
//
// Output: <out>/shots/*.png (a page over 14 screens is kept as its first 9 and its last 2: "truncated" in the manifest).
import { execFileSync, spawn, spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const at = argv.indexOf(`--${name}`);
  return at >= 0 ? argv[at + 1] : fallback;
};
const flag = (name) => argv.includes(`--${name}`);

const REPO = path.resolve(opt("repo", process.env.ATLAS_REPO ?? path.join(HERE, "../../..")));
const OUT = path.resolve(opt("out", process.env.ATLAS_OUT ?? "atlas-out"));
const BASE = opt("base", process.env.ATLAS_BASE ?? "http://localhost:3008").replace(/\/$/, "");
const DJANGO_PORT = opt("django-port", "8108");
const ENV_FILE = opt("env", process.env.ATLAS_ENV);
const ONLY = opt("only") ? new RegExp(opt("only")) : null;
const WEB = path.join(REPO, "examleaf-web");
const FRONT = path.join(REPO, "examleaf-frontend");
const PY = path.join(WEB, ".venv/bin/python");
const SHOTS = path.join(OUT, "shots");
const CREDS = path.join(OUT, "creds.json");
const DJANGO_LOG = path.join(OUT, "django.log");
const WEB_PORT = new URL(BASE).port || "80";
fs.mkdirSync(SHOTS, { recursive: true });

const { chromium } = createRequire(path.join(FRONT, "package.json"))("playwright");

// ---------------------------------------------------------------------------------------------------- environment
function readEnvFile(file) {
  const env = {};
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const m = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
    if (m) env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return env;
}
const DJANGO_ENV = { ...process.env, ...(ENV_FILE ? readEnvFile(ENV_FILE) : {}) };

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

// ---------------------------------------------------------------------------------------------------- Django
/** Runs Python in the project's shell (`manage.py shell`), returns what it printed. */
function shell(code, extraEnv = {}) {
  const result = spawnSync(PY, ["manage.py", "shell"], {
    cwd: WEB,
    input: code,
    env: { ...DJANGO_ENV, ...extraEnv },
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.status !== 0) {
    const said = result.stderr.toString().split("\n").filter((line) => !line.startsWith("{")).slice(-14).join("\n");
    throw new Error(`manage.py shell failed:\n${said}`);
  }
  return result.stdout.toString();
}
/** One of seed.py's phases; returns what it said (its ATLAS lines are on stderr). */
function seed(phase) {
  const result = spawnSync(PY, ["manage.py", "shell"], {
    cwd: WEB,
    input: fs.readFileSync(path.join(HERE, "seed.py")),
    env: { ...DJANGO_ENV, ATLAS_PHASE: phase, ATLAS_CREDS: CREDS },
    maxBuffer: 256 * 1024 * 1024,
  });
  const said = `${result.stdout}\n${result.stderr}`;
  if (result.status !== 0) throw new Error(`seed ${phase} failed:\n${said.split("\n").filter((line) => !line.startsWith("{")).slice(-25).join("\n")}`);
  for (const line of said.split("\n")) if (line.startsWith("ATLAS ")) log(`  ${line}`);
  return said;
}
/** Evaluates a Python expression in the project's shell and returns it as JSON. */
function pyJson(expression, imports = "") {
  const out = shell(`${imports}\nimport json\nprint("@@" + json.dumps(${expression}, default=str))`);
  return JSON.parse(out.split("@@").pop());
}
function manage(...args) {
  return execFileSync(PY, ["manage.py", ...args], { cwd: WEB, env: DJANGO_ENV, stdio: ["ignore", "pipe", "pipe"] }).toString();
}

// ---------------------------------------------------------------------------------------------------- servers
const listening = (port) => {
  try {
    return execFileSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"]).toString().trim().split("\n").filter(Boolean);
  } catch {
    return [];
  }
};
async function answers(url, timeout = 60000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await fetch(url).then((r) => r.status < 500, () => false)) return true;
    await sleep(400);
  }
  return false;
}
const servers = {
  stop(which = "both") {
    if (which !== "frontend") for (const pid of listening(DJANGO_PORT)) process.kill(Number(pid));
    if (which !== "django") for (const pid of listening(WEB_PORT)) process.kill(Number(pid));
  },
  async startDjango() {
    if (listening(DJANGO_PORT).length) return;
    const out = fs.openSync(DJANGO_LOG, "a");
    spawn(PY, ["manage.py", "runserver", DJANGO_PORT, "--noreload"], { cwd: WEB, env: DJANGO_ENV, stdio: ["ignore", out, out], detached: true }).unref();
    if (!(await answers(`http://localhost:${DJANGO_PORT}/health/web/`))) throw new Error("Django did not start");
  },
  async startFrontend() {
    if (listening(WEB_PORT).length) return;
    const out = fs.openSync(path.join(OUT, "next.log"), "a");
    spawn("npm", ["start"], {
      cwd: FRONT,
      env: { ...DJANGO_ENV, PORT: WEB_PORT, NEXT_PUBLIC_SITE_URL: BASE, API_INTERNAL_BASE: `http://localhost:${DJANGO_PORT}` },
      stdio: ["ignore", out, out],
      detached: true,
    }).unref();
    if (!(await answers(`${BASE}/api/health/`))) throw new Error("the frontend did not start");
  },
  /** Django down, the frontend up with empty caches: what a visitor sees while the backend is away. */
  async outage() {
    this.stop();
    await sleep(1200);
    fs.rmSync(path.join(FRONT, ".next/cache/fetch-cache"), { recursive: true, force: true });
    await this.startFrontend();
  },
  async recover() {
    await this.startDjango();
  },
  /** Both servers again with empty caches: Django's page cache lives in the process, Next's data cache on disk. */
  async refresh() {
    this.stop();
    await sleep(1200);
    fs.rmSync(path.join(FRONT, ".next/cache/fetch-cache"), { recursive: true, force: true });
    await this.startDjango();
    await this.startFrontend();
  },
};

// ---------------------------------------------------------------------------------------------------- credentials
const creds = () => JSON.parse(fs.readFileSync(CREDS, "utf8"));
function base32(text) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const bytes = [];
  for (const char of text.replace(/=+$/, "").toUpperCase()) {
    value = (value << 5) | alphabet.indexOf(char);
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return Buffer.from(bytes);
}
/** The authenticator app's code (RFC 6238: 6 digits, 30 s, SHA-1), as allauth.mfa computes it from the secret. */
function totp(secret, at = Date.now()) {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30000)));
  const hash = crypto.createHmac("sha1", base32(secret)).update(counter).digest();
  const o = hash[19] & 15;
  const value = (((hash[o] & 127) << 24) | (hash[o + 1] << 16) | (hash[o + 2] << 8) | hash[o + 3]) % 1e6;
  return String(value).padStart(6, "0");
}
let lastTotpWindow = -1;
/** A code that allauth has not seen in this 30 s window (it refuses a code twice): waits for the next window if needed. */
async function freshTotp(secret) {
  while (Math.floor(Date.now() / 30000) === lastTotpWindow) await sleep(1000);
  lastTotpWindow = Math.floor(Date.now() / 30000);
  return totp(secret);
}

/** The console email backend prints a message as quoted-printable: lines cut with "=" and "=3D" for "=". */
const quotedPrintable = (text) => text.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));

/** The newest 6-digit code or link emailed to `to` after the log had `after` characters (console email backend). */
async function emailed(to, pattern, after = 0, timeout = 20000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const text = fs.readFileSync(DJANGO_LOG, "utf8");
    const start = text.lastIndexOf(`To: ${to}`);
    if (start >= after && start !== -1) {
      const found = pattern.exec(quotedPrintable(text.slice(start, start + 30000)));
      if (found) return found[1] ?? found[0];
    }
    await sleep(250);
  }
  throw new Error(`nothing emailed to ${to}`);
}
const CODE = /^(\d{6})\r?$/m;
const logLength = () => fs.statSync(DJANGO_LOG).size;

// ---------------------------------------------------------------------------------------------------- browser
const VIEWPORTS = {
  desktop: { label: "desktop 1280", options: { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 } },
  phone: {
    label: "phone 390",
    options: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  },
};
const statePath = (who) => path.join(OUT, `${who}.state.json`);
let browser;
const newContext = (vp, who = "anon", extra = {}) =>
  browser.newContext({
    ...VIEWPORTS[vp].options,
    reducedMotion: "reduce",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
    ...(who !== "anon" && fs.existsSync(statePath(who)) ? { storageState: statePath(who) } : {}),
    ...extra,
  });

/** The admin's Save row sticks to the bottom of the screen: in a picture of the whole page it would sit over the
 *  middle of the form, so it is put at the end of the form, where it belongs. */
const ADMIN_PRINT = ".submit-row{position:static!important;bottom:auto!important}";

/** After a navigation: fonts, lazy pictures (scrolled into view and back), the network quiet. */
async function settle(page, { keepScroll = false } = {}) {
  const scrolled = keepScroll ? await page.evaluate(() => window.scrollY).catch(() => 0) : 0;
  await page.waitForLoadState("load").catch(() => {});
  if (/^\/(admin|learn)\//.test(new URL(page.url()).pathname)) await page.addStyleTag({ content: ADMIN_PRINT }).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready).catch(() => {});
  await page
    .evaluate(async () => {
      const step = window.innerHeight;
      const end = Math.min(document.documentElement.scrollHeight, 60000);
      for (let y = 0; y < end; y += step) {
        window.scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 40));
      }
      window.scrollTo(0, 0);
    })
    .catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  await page
    .evaluate(() =>
      Promise.all([...document.images].map((image) => (image.complete ? 0 : new Promise((r) => (image.onload = image.onerror = r))))),
    )
    .catch(() => {});
  if (keepScroll) await page.evaluate((y) => window.scrollTo(0, y), scrolled).catch(() => {});
  await page.waitForTimeout(250);
}

/** A login through the real pages; the state (cookies) is kept for the contexts that follow. */
async function login(who, { page: given, vp = "desktop", next, stopAtSecondStep = false } = {}) {
  const user = creds()[who];
  const ctx = given ? null : await newContext(vp);
  const page = given ?? (await ctx.newPage());
  await page.goto(`${BASE}/account/login/${next ? `?next=${encodeURIComponent(next)}` : ""}`, { waitUntil: "networkidle" });
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(user.email);
  await page.locator("#password").fill(user.password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  if (who === "staff") {
    await page.waitForURL(/2fa\/authenticate/, { timeout: 20000 });
    if (stopAtSecondStep) return page;
    await page.waitForLoadState("networkidle");
    await page.locator("#code").fill(await freshTotp(user.totp_secret));
    await page.getByRole("button", { name: "Continue" }).click();
  }
  await page.waitForURL((url) => !/\/account\/(login|2fa)/.test(url.pathname), { timeout: 20000 });
  await page.waitForLoadState("networkidle");
  await (given ?? page).context().storageState({ path: statePath(who) });
  if (ctx) await ctx.close();
  return page;
}
async function ensureLogin(who) {
  if (!fs.existsSync(statePath(who))) {
    log(`log in as ${who} through the real pages`);
    await login(who, { next: who === "staff" ? "/admin/" : undefined });
  }
}

// ---------------------------------------------------------------------------------------------------- captures
const captures = [];
const failures = [];
let counter = 0;
const MAX_SCREENS = 14; // a page taller than this many screens is kept as its first TOP_SCREENS and last TAIL_SCREENS
const TOP_SCREENS = 9;
const TAIL_SCREENS = 2;

/** Links that carry a secret (an order's token, a parent's link, a reset key) are shown with a placeholder. */
const redact = (url) =>
  url
    .replace(/(\/t\/)[^/?#]+/, "$1<token>")
    .replace(/(\/c\/)[^/?#]+/, "$1<token>")
    .replace(/(\/key\/)[^/?#]+/, "$1<key>")
    .replace(/(\/orders\/t\/)[^/?#]+/, "$1<token>");

/** One picture of the page as it is now (full page unless `full: false`); returns the manifest row. */
async function snap(page, meta) {
  await settle(page, { keepScroll: meta.full === false }); // a screen-only picture is of where the page has been scrolled to
  const vp = VIEWPORTS[meta.vp];
  const id = `${String(++counter).padStart(3, "0")}-${meta.id}-${meta.vp}`;
  const file = `${id}.png`;
  const dpr = vp.options.deviceScaleFactor;
  const screen = vp.options.viewport.height;
  const full = meta.full !== false;
  const height = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight ?? 0));
  const width = vp.options.viewport.width;
  const row = {
    id,
    area: meta.area,
    scene: meta.scene_id,
    order: meta.order,
    seq: counter,
    route: meta.route,
    pattern: meta.pattern && meta.pattern !== meta.route ? meta.pattern : undefined,
    state: meta.state,
    who: meta.who ?? "anonymous",
    viewport: meta.vp,
    viewport_label: vp.label,
    title: await page.title(),
    url: redact(page.url().replace(BASE, "") || "/"),
    status: meta.status,
    file: `shots/${file}`,
    dpr,
    width: width * dpr,
    page_height_css: height,
    full,
  };
  if (full && height > screen * MAX_SCREENS) {
    const top = screen * TOP_SCREENS;
    const tail = screen * TAIL_SCREENS;
    await page.screenshot({ path: path.join(SHOTS, file), fullPage: true, clip: { x: 0, y: 0, width, height: top } });
    const tailFile = file.replace(/\.png$/, ".tail.png");
    await page.screenshot({ path: path.join(SHOTS, tailFile), fullPage: true, clip: { x: 0, y: height - tail, width, height: tail } });
    row.truncated = { top_css: top, tail_css: tail, tail_file: `shots/${tailFile}`, omitted_css: height - top - tail };
    row.height = (top + tail) * dpr;
  } else {
    await page.screenshot({ path: path.join(SHOTS, file), fullPage: full });
    row.height = (full ? height : screen) * dpr;
  }
  captures.push(row);
  log(`  ${id}  ${row.title.slice(0, 50)}  [${row.page_height_css}px${row.truncated ? " truncated" : ""}]`);
  return row;
}

// ---------------------------------------------------------------------------------------------------- scenes
const AREAS = {
  discover: "A. Discover",
  buy: "B. Buy",
  after: "C. After the order",
  record: "D. Record",
  account: "E. Account and data rights",
  signin: "F. Sign-in and recovery",
  system: "G. System, errors and offline",
  adminDash: "Admin 1. Dashboard",
  adminCatalogue: "Admin 2. Catalogue",
  adminOrders: "Admin 3. Orders and customers",
  adminOffers: "Admin 4. Offers, reviews and quotations",
  adminCourse: "Admin 5. Revision course",
  adminPeople: "Admin 6. People and roles",
  adminContent: "Admin 7. Papers and pages",
  adminSystem: "Admin 8. System",
  django: "Django pages outside the admin",
};
const scenes = [];
/** A scene: its id, TOC area, route shown in the caption, state, options and the steps that bring the page up. */
function S(id, area, route, state, options, run) {
  if (typeof options === "function" || typeof options === "string") [options, run] = [{}, options];
  if (typeof run === "string") {
    const url = run;
    run = (h) => h.goto(url);
  }
  run ??= (h) => h.goto(route);
  scenes.push({ kind: "scene", id, area, route, state, options, run });
}
/** A step with no picture (seeding, restarting). */
function STEP(id, run) {
  scenes.push({ kind: "step", id, run });
}

/** What a scene's steps get: the page, and the helpers around it. */
function helpers(page, ctx, vp, scene) {
  const h = {
    page,
    ctx,
    vp,
    BASE,
    phone: vp === "phone",
    creds: creds,
    shell,
    pyJson,
    seed,
    manage,
    emailed,
    CODE,
    logLength,
    sleep,
    servers,
    async goto(url, options = {}) {
      const response = await page.goto(BASE + url, { waitUntil: "load", ...options });
      h.status = response?.status();
      await settle(page);
      return response;
    },
    /** An extra picture inside a scene (the scene's own final picture is taken after its steps). */
    async snap(over = {}) {
      return snap(page, { ...scene, ...scene.options, ...over, vp, status: h.status });
    },
    /** Hide the toasts (they stay 6 s): for pictures that are not about them. */
    async noToasts() {
      await page.addStyleTag({ content: "[data-toast]{display:none!important}" });
    },
    async click(name, root = page) {
      await root.getByRole("button", { name }).first().click();
    },
    async fill(selector, value) {
      await page.locator(selector).fill(value);
    },
  };
  return h;
}

// ---------------------------------------------------------------------------------------------------- the scenes
// The atlas's scenes: which page, in which state, for whom. capture.mjs runs them in order, each at both widths.
// S(id, area, route, state, options, run): `run` is a path to open, or steps (h) => ...; the picture is taken after the
// steps unless they took their own (h.snap) or return "none". Options: who ("student", "staff"), vps (["phone"]),
// full (false: the screen only, for dialogs and toasts), pattern (the documented route), context (Playwright options).
function register(k) {
  const { S, STEP, AREAS: A, creds, seed, servers, sleep, login, freshTotp, BASE, pyJson, shell, manage, emailed, CODE, logLength, fs, path, OUT } = k;
  const STUDENT = () => creds().student;
  const open = async (h, selector) => {
    await h.page.locator(selector).first().scrollIntoViewIfNeeded();
  };

  // ============================================================================================ preparation
  k.state = {};
  STEP("prepare", async () => {
    seed("base");
    seed("catalogue");
    await servers.refresh();
    // book codes as printed: one for the student to type, others for the admin's list (only their hashes are kept)
    k.state.bookCode = manage("make_book_codes", "PHY", "1", "--batch", "ATLAS-2027-1").split("\n")[1].split(",")[0];
    for (const subject of ["CHE", "MAT", "BIO"]) manage("make_book_codes", subject, "4", "--batch", "ATLAS-2027-1");
  });

  // ============================================================================================ A. Discover
  S("home", A.discover, "/", "anonymous", "/");
  S("home-menu", A.discover, "/", "anonymous, phone: the menu open", { vps: ["phone"], full: false }, async (h) => {
    await h.goto("/");
    await h.page.getByRole("button", { name: "Menu" }).click();
    await h.page.waitForTimeout(400);
  });
  S("book-physics", A.discover, "/books/physics-2027/", "anonymous: a book with its open sample", { pattern: "/books/<slug>/" }, "/books/physics-2027/");
  S("book-physics-in", A.discover, "/books/physics-2027/", "signed in: the record is kept, not offered", { who: "student", pattern: "/books/<slug>/" }, "/books/physics-2027/");
  S("book-chemistry", A.discover, "/books/chemistry-2027/", "anonymous: a book without an open sample", { pattern: "/books/<slug>/" }, "/books/chemistry-2027/");
  S("solutions-gated", A.discover, "/s/PHY-E02/", "anonymous: the solutions are gated (register or log in)", { pattern: "/s/<code>/" }, "/s/PHY-E02/");
  S("solutions-open", A.discover, "/s/PHY-E01/", "anonymous: the open sample, readable without an account", { pattern: "/s/<code>/" }, "/s/PHY-E01/");
  S("solutions-unknown", A.discover, "/s/ZZZ-E99/", "anonymous: no such paper (404)", { pattern: "/s/<code>/" }, "/s/ZZZ-E99/");
  S("about", A.discover, "/about/", "anonymous", "/about/");
  for (const page of ["privacy", "terms", "refunds", "shipping"]) {
    S(page, A.discover, `/${page}/`, "anonymous (a legal page from the admin's Pages)", { pattern: "/privacy/ /terms/ /refunds/ /shipping/ /contact/" }, `/${page}/`);
  }
  S("contact", A.discover, "/contact/", "anonymous: the page and its form", { pattern: "/privacy/ /terms/ /refunds/ /shipping/ /contact/" }, "/contact/");
  S("contact-errors", A.discover, "/contact/", "anonymous: the form sent empty", async (h) => {
    await h.goto("/contact/");
    await h.page.getByRole("button", { name: "Send the message" }).click();
    await h.page.waitForTimeout(500);
    await h.page.locator("#name").scrollIntoViewIfNeeded();
  });
  S("contact-sent", A.discover, "/contact/", "anonymous: the message sent", async (h) => {
    await h.goto("/contact/");
    await h.fill("#name", "Atlas Visitor");
    await h.fill("#email", "atlas-visitor@example.com");
    await h.fill("#message", "I scanned the QR code on Physics paper E-02 and the solution of 2(c) has a different unit from the question. Please check.");
    await h.page.getByRole("button", { name: "Send the message" }).click();
    await h.page.waitForTimeout(1500);
    await h.page.locator("#name, [role=status]").first().scrollIntoViewIfNeeded().catch(() => {});
  });
  S("offline", A.discover, "/offline/", "anonymous: the page the service worker shows without a connection", "/offline/");
  S("revision-anon", A.discover, "/revision/", "anonymous: chapters, marks, what is free", "/revision/");
  S("parent-link-invalid", A.discover, "/c/<token>/", "a parent's link that does not work (expired or replaced)", "/c/not-a-real-link/");
  S("parent-link-valid", A.discover, "/c/<token>/", "a parent's link: consent confirmed", async (h) => {
    const token = pyJson(
      `parent_signer(u.parent_contact).sign(int_to_base36(u.pk))`,
      `from accounts.models import User\nfrom accounts.views import parent_signer\nfrom django.utils.http import int_to_base36\nu = User.objects.get(email="atlas-minor@example.com")`,
    );
    await h.goto(`/c/${token}/`);
  });

  // ============================================================================================ B. Buy
  S("shop", A.buy, "/shop/", "anonymous: the catalogue", "/shop/");
  S("shop-category", A.buy, "/shop/category/sample-papers/", "a shelf of the category tree", { pattern: "/shop/category/<slug>/" }, "/shop/category/sample-papers/");
  S("shop-collection", A.buy, "/shop/collection/physics/", "a hand-picked collection", { pattern: "/shop/collection/<slug>/" }, "/shop/collection/physics/");
  S("shop-category-unknown", A.buy, "/shop/category/no-such-shelf/", "no such shelf (404)", { pattern: "/shop/category/<slug>/" }, "/shop/category/no-such-shelf/");
  S("product-sample", A.buy, "/shop/physics-sample-papers-2027/", "a Sample Papers book: pictures, choice with the bundle, reviews", { pattern: "/shop/<slug>/" }, "/shop/physics-sample-papers-2027/");
  S("product-solutions", A.buy, "/shop/physics-solutions-2027/", "a Solutions book (no cover picture)", { pattern: "/shop/<slug>/" }, "/shop/physics-solutions-2027/");
  S("product-bundle", A.buy, "/shop/physics-bundle-2027/", "a bundle", { pattern: "/shop/<slug>/" }, "/shop/physics-bundle-2027/");
  S("product-unknown", A.buy, "/shop/no-such-book/", "no such book (404)", { pattern: "/shop/<slug>/" }, "/shop/no-such-book/");
  S("school-orders", A.buy, "/shop/school-orders/", "anonymous: the quotation request form", "/shop/school-orders/");
  S("school-orders-errors", A.buy, "/shop/school-orders/", "the form sent empty", async (h) => {
    await h.goto("/shop/school-orders/");
    await h.page.getByRole("button", { name: "Ask for a quotation" }).click();
    await h.page.waitForTimeout(500);
  });
  S("school-orders-sent", A.buy, "/shop/school-orders/", "the request sent", async (h) => {
    await h.goto("/shop/school-orders/");
    await h.fill("#school", "Demo Higher Secondary School");
    await h.fill("#contact_name", "Atlas Teacher");
    await h.fill("#email", "atlas-teacher@example.com");
    await h.fill("#phone", "9864012345");
    await h.fill("#gstin", "18AAAPA1234A1ZS");
    await h.fill("#delivery_pin", "781005");
    await h.fill("#copies-physics-bundle-2027", "40");
    await h.fill("#copies-chemistry-solutions-2027", "20");
    await h.fill("#note", "Delivery before the school's pre-test in December, please.");
    await h.page.getByRole("button", { name: "Ask for a quotation" }).click();
    await h.page.waitForTimeout(2500);
  });
  S("cart-empty", A.buy, "/cart/", "anonymous: nothing in the cart", "/cart/");

  // a guest from the product page to the page that waits for payment
  S("guest-shopping", A.buy, "/cart/", "guest journey", { vps: ["desktop", "phone"] }, async (h) => {
    const { page } = h;
    await h.goto("/shop/physics-bundle-2027/");
    await h.page.getByRole("button", { name: "Add to cart" }).first().click();
    await page.waitForURL(/\/cart\//);
    await page.waitForTimeout(600);
    await h.snap({ id: "cart-toast", route: "/cart/", state: "guest: the toast after Add to cart", full: false });
    await h.noToasts();
    await h.goto("/shop/chemistry-sample-papers-2027/");
    await page.getByRole("button", { name: "Add to cart" }).first().click();
    await page.waitForURL(/\/cart\//);
    await h.noToasts();
    await h.snap({ id: "cart-guest", route: "/cart/", state: "guest: two books, the offer's saving line" });
    await page.getByRole("button", { name: "Remove" }).first().click();
    await page.waitForTimeout(400);
    await h.snap({ id: "cart-remove-dialog", route: "/cart/", state: "guest: Remove asks first", full: false });
    await page.getByRole("button", { name: "Keep it" }).click();
    await page.locator("#code").fill("NOSUCHCODE");
    await page.getByRole("button", { name: "Apply" }).click();
    await page.waitForTimeout(1200);
    await h.snap({ id: "cart-coupon-error", route: "/cart/", state: "guest: a coupon that does not apply" });
    await page.locator("#code").fill("welcome10");
    await page.getByRole("button", { name: "Apply" }).click();
    await page.waitForTimeout(1500);
    await h.noToasts();
    await h.snap({ id: "cart-coupon", route: "/cart/", state: "guest: the coupon applied (any case)" });
    await page.getByRole("link", { name: "Checkout" }).first().click();
    await page.waitForURL(/\/checkout\//);
    await settleQuiet(h);
    await h.snap({ id: "checkout-guest", route: "/checkout/", state: "guest: address, delivery, payment" });
    await page.getByRole("button", { name: "Continue to payment" }).click();
    await page.waitForTimeout(800);
    await h.snap({ id: "checkout-guest-errors", route: "/checkout/", state: "guest: the form sent empty" });
    await page.locator("#email").fill("atlas-guest@example.com");
    await page.locator("#name").fill("Atlas Guest");
    await page.locator("#phone").fill("9864054321");
    await page.locator("#line1").fill("7 Test Lane");
    await page.locator("#pin").fill("786001");
    await page.waitForTimeout(1500);
    if (!(await page.locator("#city").inputValue())) await page.locator("#city").fill("Dibrugarh");
    await h.snap({ id: "checkout-guest-filled", route: "/checkout/", state: "guest: filled; the PIN code gave the district and state" });
    await page.getByRole("button", { name: "Continue to payment" }).click();
    await page.waitForURL(/\/checkout\/t\/[^/]+\/pay\//, { timeout: 20000 });
    await settleQuiet(h);
    const token = /\/checkout\/t\/([^/]+)\//.exec(page.url())[1];
    await h.snap({ id: "pay-guest", route: "/checkout/t/<token>/pay/", pattern: "/checkout/t/<token>/pay/", state: "guest: the order waits for payment (Razorpay is not set up here)" });
    await h.goto(`/checkout/t/${token}/done/`);
    await h.snap({ id: "done-guest", route: "/checkout/t/<token>/done/", pattern: "/checkout/t/<token>/done/", state: "guest: the done page of an order not yet paid" });
    await h.goto(`/orders/t/${token}/`);
    await h.snap({ id: "order-guest", area: A.after, route: "/orders/t/<token>/", pattern: "/orders/t/<token>/", state: "guest: the order by its emailed link" });
    h.guestToken = token;
    return "none";
  });
  S("order-guest-unknown", A.after, "/orders/t/<token>/", "a link that matches no order (404)", "/orders/t/not-a-real-link/");
  S("lookup", A.after, "/orders/lookup/", "anonymous: find an order placed without an account", "/orders/lookup/");
  S("lookup-sent", A.after, "/orders/lookup/", "the link asked for (the page does not say whether the order exists)", async (h) => {
    await h.goto("/orders/lookup/");
    await h.fill("#number", "EL-2026-000001");
    await h.fill("#email", "atlas-guest@example.com");
    await h.page.getByRole("button", { name: "Email me the link" }).click();
    await h.page.waitForTimeout(1500);
  });
  S("lookup-errors", A.after, "/orders/lookup/", "the form sent empty", async (h) => {
    await h.goto("/orders/lookup/");
    await h.page.getByRole("button", { name: "Email me the link" }).click();
    await h.page.waitForTimeout(500);
  });

  // ============================================================================================ F. Sign-in and recovery
  S("login", A.signin, "/account/login/", "anonymous: a code by email first, a passkey, the password folded away", "/account/login/");
  S("login-password", A.signin, "/account/login/", "the password fold open", async (h) => {
    await h.goto("/account/login/");
    await h.page.getByText("Log in with email and password").click();
    await h.page.waitForTimeout(300);
  });
  S("login-wrong", A.signin, "/account/login/", "a wrong password", async (h) => {
    await h.goto("/account/login/");
    await h.page.getByText("Log in with email and password").click();
    await h.fill("#login", "atlas-nobody@example.com");
    await h.fill("#password", "not-the-password-1");
    await h.page.getByRole("button", { name: "Log in", exact: true }).click();
    await h.page.waitForTimeout(1500);
  });
  S("login-code", A.signin, "/account/login/", "the code asked for: the six digits are typed here", async (h) => {
    await h.goto("/account/login/");
    await h.fill("#email", `atlas-nobody-code-${h.vp}@example.com`);
    await h.page.getByRole("button", { name: "Email me a code" }).click();
    await h.page.waitForTimeout(1800);
  });
  S("login-code-wrong", A.signin, "/account/login/", "a wrong code", async (h) => {
    await h.goto("/account/login/");
    await h.fill("#email", `atlas-nobody-wrong-${h.vp}@example.com`);
    await h.page.getByRole("button", { name: "Email me a code" }).click();
    await h.page.waitForTimeout(1500);
    await h.page.locator("input[autocomplete=one-time-code], #code").first().fill("000000");
    await h.page.getByRole("button", { name: "Log in", exact: true }).click().catch(() => {});
    await h.page.waitForTimeout(1500);
  });
  S("signup", A.signin, "/account/signup/", "anonymous: the registration form", "/account/signup/");
  S("signup-errors", A.signin, "/account/signup/", "the form sent empty", async (h) => {
    await h.goto("/account/signup/");
    await h.page.getByRole("button", { name: "Register" }).last().click();
    await h.page.waitForTimeout(600);
  });
  S("signup-minor", A.signin, "/account/signup/", "a date of birth under 18 asks for a parent", async (h) => {
    await h.goto("/account/signup/");
    await h.fill("#date_of_birth", `${new Date().getFullYear() - 15}-05-02`);
    await h.page.waitForTimeout(500);
  });
  S("signup-flow", A.signin, "/account/signup/", "registration journey", async (h) => {
    const { page } = h;
    const email = `atlas-signup-${h.vp}@example.com`;
    await h.goto("/account/signup/?next=%2Fs%2FPHY-E02%2F");
    await h.fill("#full_name", "Atlas Newcomer");
    await h.fill("#email", email);
    await h.fill("#password", "Atlas-Sample-Pass-2026");
    await h.fill("#password2", "Atlas-Sample-Pass-2026");
    await page.locator("#class_level").selectOption("12");
    await page.locator("#board").selectOption("1");
    await h.fill("#district", "Kamrup Metro");
    await h.fill("#date_of_birth", "2008-04-20");
    await page.locator("#consent").check();
    await h.snap({ id: "signup-filled", route: "/account/signup/", state: "the registration form filled in (with ?next= from a QR code)" });
    const mark = logLength();
    await page.getByRole("button", { name: "Register" }).last().click();
    await page.waitForURL(/verify-email/, { timeout: 20000 });
    await h.snap({ id: "verify-email", route: "/account/verify-email/", state: "the six-digit code asked for after registering" });
    await page.locator("input[autocomplete=one-time-code], #code").first().fill("000000");
    await page.getByRole("button", { name: /Confirm|Continue|Verify/ }).first().click();
    await page.waitForTimeout(1500);
    await h.snap({ id: "verify-email-wrong", route: "/account/verify-email/", state: "a wrong code" });
    const code = await emailed(email, CODE, mark);
    await page.reload({ waitUntil: "load" }); // a fresh field: the digits typed before stay in the old one
    await page.waitForSelector("input[autocomplete=one-time-code], #code");
    await page.locator("input[autocomplete=one-time-code], #code").first().fill(code);
    await page.getByRole("button", { name: /Confirm|Continue|Verify/ }).first().click();
    await page.waitForURL(/\/s\/PHY-E02\//, { timeout: 20000 });
    await h.snap({ id: "signup-done", route: "/s/<code>/", pattern: "/s/<code>/", state: "the code accepted: back on the paper whose QR code was scanned (a new account is gated until its email is confirmed: it is)", who: "student" });
    return "none";
  });
  S("verify-email-none", A.signin, "/account/verify-email/", "no confirmation waiting", "/account/verify-email/");
  S("reset-request", A.signin, "/account/password/reset/", "anonymous: forgot your password", "/account/password/reset/");
  // the way a visitor gets there: from the log-in page (whose load sets the CSRF cookie the reset form's POST needs)
  const toReset = async (h) => {
    await h.goto("/account/login/");
    await h.page.getByText("Log in with email and password").click();
    await h.page.getByRole("link", { name: "Forgot your password?" }).click();
    await h.page.waitForURL(/password\/reset\/$/);
    await h.page.waitForLoadState("networkidle");
  };
  S("reset-sent", A.signin, "/account/password/reset/", "the link asked for", async (h) => {
    await toReset(h);
    await h.fill("#email", STUDENT().email);
    await h.page.getByRole("button", { name: "Email me a link" }).click();
    await h.page.waitForTimeout(2000);
  });
  S("reset-key-bad", A.signin, "/account/password/reset/key/<key>/", "a link that does not work any more", { pattern: "/account/password/reset/key/<key>/" }, "/account/password/reset/key/abc-def/");
  S("reset-key-ok", A.signin, "/account/password/reset/key/<key>/", "the emailed link: choose a new password", { pattern: "/account/password/reset/key/<key>/" }, async (h) => {
    const mark = logLength();
    await toReset(h);
    await h.fill("#email", STUDENT().email);
    await h.page.getByRole("button", { name: "Email me a link" }).click();
    const link = await emailed(STUDENT().email, /(http:\/\/[^\s]+\/account\/password\/reset\/key\/[^\s/]+\/)/, mark);
    await h.goto(link.replace(BASE, ""));
  });
  S("2fa-none", A.signin, "/account/2fa/authenticate/", "no second step waiting", "/account/2fa/authenticate/");
  S("logout", A.signin, "/account/logout/", "after logging out", "/account/logout/");
  S("account-gated", A.account, "/account/orders/", "anonymous: an account page sends the visitor to log in, and back to it afterwards", { pattern: "/account/…" }, "/account/orders/");

  // ============================================================================================ staff log-in
  // The staff log in with a password and then the authenticator app's code: the second step's page is pictured on both
  // widths, and the desktop run goes on to sign in (its cookies serve every Django page that follows).
  S("2fa-step", A.signin, "/account/2fa/authenticate/", "staff: after the password, the authenticator app's code", async (h) => {
    const user = creds().staff;
    await h.goto("/account/login/?next=%2Fadmin%2F");
    await h.page.getByText("Log in with email and password").click();
    await h.fill("#login", user.email);
    await h.fill("#password", user.password);
    await h.page.getByRole("button", { name: "Log in", exact: true }).click();
    await h.page.waitForURL(/2fa\/authenticate/, { timeout: 20000 });
    await h.page.waitForLoadState("networkidle");
    await h.snap({ id: "2fa-step", route: "/account/2fa/authenticate/" });
    await h.fill("#code", "000000");
    await h.page.getByRole("button", { name: "Continue" }).click();
    await h.page.waitForTimeout(1500);
    await h.snap({ id: "2fa-step-wrong", route: "/account/2fa/authenticate/", state: "staff: a wrong code" });
    if (!h.phone) {
      await h.fill("#code", await k.freshTotp(user.totp_secret));
      await h.page.getByRole("button", { name: "Continue" }).click();
      await h.page.waitForURL(/\/admin\//, { timeout: 20000 });
      await h.ctx.storageState({ path: k.statePath("staff") });
    }
    return "none";
  });

  // ============================================================================================ the student, a new account
  const stu = { who: "student" };
  S("home-in", A.discover, "/", "signed in", stu, "/");
  S("revision-locked", A.discover, "/revision/", "signed in, nothing open yet: the book code and the plan", stu, "/revision/");
  S("account-empty", A.account, "/account/", "a new account: nothing yet", stu, "/account/");
  S("orders-empty", A.after, "/account/orders/", "no orders yet", stu, "/account/orders/");
  S("record-empty", A.record, "/account/record/", "nothing recorded yet", stu, "/account/record/");
  S("learning-empty", A.account, "/account/learning/", "nothing open, nothing watched", stu, "/account/learning/");
  S("addresses-empty", A.account, "/account/addresses/", "no saved address: the form for the first", stu, "/account/addresses/");
  S("address-errors", A.account, "/account/addresses/", "the address form sent empty", stu, async (h) => {
    await h.goto("/account/addresses/");
    await h.page.getByRole("button", { name: "Save the address" }).click();
    await h.page.waitForTimeout(600);
  });
  S("details", A.account, "/account/details/", "the details as registered", stu, "/account/details/");
  S("security", A.account, "/account/security/", "email, password, passkeys and the devices signed in", stu, "/account/security/");
  S("2fa-off", A.account, "/account/2fa/", "two-step log-in not set up", stu, "/account/2fa/");
  S("2fa-setup", A.account, "/account/2fa/", "the authenticator app: the QR code and the key", stu, async (h) => {
    await h.goto("/account/2fa/");
    await h.page.getByRole("button", { name: "Set up the authenticator app" }).click();
    await h.page.waitForSelector("#code");
    await h.page.waitForTimeout(800);
  });
  S("privacy", A.account, "/account/privacy/", "consent, Download my data, Delete my account", stu, "/account/privacy/");
  S("privacy-wrong", A.account, "/account/privacy/", "Download my data with a wrong password", stu, async (h) => {
    await h.goto("/account/privacy/");
    await h.fill("#password", "not-my-password");
    await h.page.getByRole("button", { name: "Download my data" }).click();
    await h.page.waitForTimeout(1500);
  });
  S("teacher", A.account, "/account/teacher/", "ask for teacher access", stu, "/account/teacher/");
  S("reauth", A.signin, "/account/reauthenticate/", "signed in: type the password again", stu, "/account/reauthenticate/");
  S("cart-empty-in", A.buy, "/cart/", "signed in: nothing in the cart", stu, "/cart/");
  S("solutions-student", A.discover, "/s/PHY-E02/", "signed in: the solutions and the record form (first screens and the end)", { ...stu, pattern: "/s/<code>/" }, "/s/PHY-E02/");

  // marks saved on a paper (a different paper on each width: a paper's attempts are the student's own record)
  S("record-save", A.record, "/s/<code>/", "saving marks on a paper's solutions page", { ...stu, pattern: "/s/<code>/" }, async (h) => {
    const code = h.phone ? "CHE-H01" : "PHY-E02";
    await h.goto(`/s/${code}/`);
    const card = h.page.locator("#record");
    await card.scrollIntoViewIfNeeded();
    await card.locator("#marks_obtained").fill("75");
    await card.getByRole("button", { name: "Save to my record" }).click();
    await h.page.waitForTimeout(800);
    await card.scrollIntoViewIfNeeded();
    await h.snap({ id: "record-form-error", area: A.record, route: `/s/${code}/`, state: "the record form: marks above the paper's full marks", full: false });
    await card.locator("#marks_obtained").fill(h.phone ? "41" : "52.5");
    await card.locator("#time_taken_minutes").fill(h.phone ? "175" : "170");
    await card.locator("#notes").fill(h.phone ? "Organic: named reactions" : "Gauss's law and the dipole");
    await card.getByRole("button", { name: "Save to my record" }).click();
    await h.page.waitForTimeout(1800);
    await card.scrollIntoViewIfNeeded();
    await h.snap({ id: "record-saved", area: A.record, route: `/s/${code}/`, state: "the record form: the marks saved, with the link to My record", full: false });
    return "none";
  });

  // a signed-in shopper from the product page to the page that waits for payment
  S("student-shopping", A.buy, "/cart/", "signed-in journey", stu, async (h) => {
    const { page } = h;
    shell(`from shop.models import Cart\nCart.objects.filter(user__email=${JSON.stringify(STUDENT().email)}).delete()`);
    await h.goto("/shop/physics-bundle-2027/");
    await page.getByRole("button", { name: "Add to cart" }).first().click();
    await page.waitForURL(/\/cart\//);
    await h.goto("/shop/mathematics-sample-papers-2027/");
    await page.getByRole("button", { name: "Add to cart" }).first().click();
    await page.waitForURL(/\/cart\//);
    await h.noToasts();
    await h.snap({ id: "cart-student", route: "/cart/", state: "signed in: two books, the offer's saving line; saved addresses wait at checkout" });
    await page.locator("#code").fill("welcome10");
    await page.getByRole("button", { name: "Apply" }).click();
    await page.waitForTimeout(1500);
    await h.noToasts();
    await h.snap({ id: "cart-student-coupon", route: "/cart/", state: "signed in: the welcome coupon applied" });
    await page.getByRole("link", { name: "Checkout" }).first().click();
    await page.waitForURL(/\/checkout\//);
    await page.waitForLoadState("networkidle");
    const newAddress = await page.locator("#name").waitFor({ state: "visible", timeout: 6000 }).then(() => true, () => false);
    await h.snap({ id: "checkout-student", route: "/checkout/", state: newAddress ? "signed in, no saved address: the address form" : "signed in: the saved address chosen" });
    if (newAddress) {
      await page.getByRole("button", { name: "Continue to payment" }).click();
      await page.waitForTimeout(800);
      await h.snap({ id: "checkout-student-errors", route: "/checkout/", state: "signed in: the form sent empty" });
      await page.locator("#name").fill("Atlas Student");
      await page.locator("#phone").fill("9864012345");
      await page.locator("#line1").fill("12 Demo Road");
      await page.locator("#line2").fill("Near the park");
      await page.locator("#pin").fill("781001");
      await page.waitForTimeout(1500);
      if (!(await page.locator("#city").inputValue())) await page.locator("#city").fill("Guwahati");
      await h.snap({ id: "checkout-student-filled", route: "/checkout/", state: "signed in: filled; the PIN code gave the district and state; the address is kept for next time" });
    }
    await page.getByRole("button", { name: "Continue to payment" }).click();
    await page.waitForURL(/\/checkout\/EL-[^/]+\/pay\//, { timeout: 20000 });
    await page.waitForLoadState("networkidle");
    const number = /\/checkout\/(EL-[^/]+)\//.exec(page.url())[1];
    await h.snap({ id: "pay-student", route: "/checkout/<number>/pay/", pattern: "/checkout/<number>/pay/", state: "signed in: the order waits for payment (Razorpay is not set up here)" });
    await h.goto(`/account/orders/${number}/`);
    await h.snap({ id: "order-pending", area: A.after, route: "/account/orders/<number>/", pattern: "/account/orders/<number>/", state: "awaiting payment: Pay now, Cancel the order" });
    return "none";
  });
  S("orders-pending", A.after, "/account/orders/", "one order awaiting payment", stu, "/account/orders/");

  // the book code printed in a book opens a subject
  S("revision-redeem", A.discover, "/revision/", "signed in: a book code typed", { ...stu, vps: ["desktop"] }, async (h) => {
    await h.goto("/revision/");
    await h.fill("#code", "ABCD-EFGH-JKLM");
    await h.page.getByRole("button", { name: "Use the code" }).click();
    await h.page.waitForTimeout(1500);
    await h.page.locator("#code").scrollIntoViewIfNeeded();
    await h.snap({ id: "revision-code-wrong", area: A.discover, route: "/revision/", state: "signed in: a code that is not one of ours", full: false });
    await h.fill("#code", k.state.bookCode.toLowerCase().replace(/-/g, " "));
    await h.page.getByRole("button", { name: "Use the code" }).click();
    await h.page.waitForTimeout(2500);
    await h.snap({ id: "revision-redeemed", route: "/revision/", state: "signed in: the code accepted, Physics open for a year" });
    return "none";
  });
  S("teacher-request", A.account, "/account/teacher/", "teacher access asked for (the form sent)", { ...stu, vps: ["desktop"] }, async (h) => {
    await h.goto("/account/teacher/");
    await h.fill("#school_name", "Demo Higher Secondary School");
    await h.fill("#district", "Kamrup Metro");
    await h.fill("#subject", "Physics");
    await h.page.getByRole("button", { name: "Send" }).click();
    await h.page.waitForTimeout(1800);
  });
  S("teacher-pending", A.account, "/account/teacher/", "teacher access: waiting for ExamLeaf to check", stu, "/account/teacher/");

  // ============================================================================================ the same student, with a history
  STEP("seed-filled", async () => {
    seed("filled");
    await servers.refresh(); // stock changed: Django's page cache and Next's data cache start again
  });
  const orderNumber = (status) =>
    pyJson(`Order.objects.filter(user__email=${JSON.stringify(STUDENT().email)}, status="${status}").order_by("pk").first().number`, "from shop.models import Order");
  const ORDER = { pattern: "/account/orders/<number>/" };
  S("account", A.account, "/account/", "with orders, marks and a course open", stu, "/account/");
  S("orders", A.after, "/account/orders/", "seven orders, in every state", stu, "/account/orders/");
  for (const [status, state] of [
    ["paid", "paid: placed, not yet packed"],
    ["packed", "packed: waiting for the courier"],
    ["shipped", "shipped: the courier and the tracking number"],
    ["delivered", "delivered: its invoice and the courier's page"],
    ["cancelled", "cancelled by the student before it was paid"],
  ]) {
    S(`order-${status}`, A.after, "/account/orders/<number>/", state, { ...stu, ...ORDER }, async (h) => h.goto(`/account/orders/${orderNumber(status)}/`));
  }
  S("order-unknown", A.after, "/account/orders/EL-2026-999999/", "an order that is not this account's (404)", { ...stu, ...ORDER }, "/account/orders/EL-2026-999999/");
  S("done-paid", A.buy, "/checkout/<number>/done/", "signed in: the thank-you page of a paid order", { ...stu, pattern: "/checkout/<number>/done/" }, async (h) => h.goto(`/checkout/${orderNumber("paid")}/done/`));
  S("record", A.record, "/account/record/", "six papers: the average for each tier, every attempt", stu, "/account/record/");
  S("record-filtered", A.record, "/account/record/?subject=&tier=E", "filtered to the Easy tier", stu, async (h) => {
    await h.goto("/account/record/");
    await h.page.locator("#tier").selectOption({ label: "Easy" });
    await h.page.getByRole("button", { name: "Show" }).click();
    await h.page.waitForLoadState("networkidle");
  });
  S("record-edit", A.record, "/account/record/<id>/edit/", "change or delete a saved attempt", { ...stu, pattern: "/account/record/<id>/edit/" }, async (h) => {
    await h.goto(`/account/record/${pyJson('Attempt.objects.filter(user__email="atlas-student@example.com").order_by("pk").first().pk', "from practice.models import Attempt")}/edit/`);
  });
  S("record-edit-unknown", A.record, "/account/record/99999/edit/", "an attempt that is not this account's (404)", { ...stu, pattern: "/account/record/<id>/edit/" }, "/account/record/99999/edit/");
  S("learning-plan", A.account, "/account/learning/", "the exam date saved: the next three days", { ...stu, vps: ["desktop"] }, async (h) => {
    await h.goto("/account/learning/");
    const date = new Date();
    date.setDate(date.getDate() + 128);
    await h.fill("#exam_date", date.toISOString().slice(0, 10));
    await h.page.getByRole("button", { name: "Save the date" }).click();
    await h.page.waitForTimeout(2500);
  });
  S("learning", A.account, "/account/learning/", "Physics open: where you left off, the plan, revise again, progress", stu, "/account/learning/");
  S("revision-open", A.discover, "/revision/", "signed in, Physics open: progress in every chapter", stu, "/revision/");
  S("addresses", A.account, "/account/addresses/", "one saved address", stu, "/account/addresses/");
  S("address-edit", A.account, "/account/addresses/", "Change opens the address in a form", stu, async (h) => {
    await h.goto("/account/addresses/");
    await h.page.getByRole("button", { name: /^Change the address/ }).click();
    await h.page.waitForTimeout(600);
  });
  S("address-delete", A.account, "/account/addresses/", "Delete asks first", { ...stu, full: false }, async (h) => {
    await h.goto("/account/addresses/");
    await h.page.getByRole("button", { name: /^Delete the address/ }).click();
    await h.page.waitForTimeout(500);
  });
  S("privacy-filled", A.account, "/account/privacy/", "what the file holds, with orders and marks", stu, "/account/privacy/");
  S("product-review", A.buy, "/shop/physics-sample-papers-2027/", "a buyer of the delivered book: the review form below the reviews", { ...stu, pattern: "/shop/<slug>/" }, "/shop/physics-sample-papers-2027/");
  S("review-sent", A.buy, "/shop/physics-sample-papers-2027/", "after the review was sent: the form is gone; only approved reviews show, so it waits for approval", { ...stu, vps: ["desktop"], pattern: "/shop/<slug>/" }, async (h) => {
    await h.goto("/shop/physics-sample-papers-2027/");
    await h.page.getByText("Review this book").scrollIntoViewIfNeeded();
    await h.page.locator("input[name=rating]").nth(1).check({ force: true });
    await h.fill("#text", "Clear solutions, and the marks for each step are shown. I wish the Hard papers had one more mock.");
    await h.page.getByRole("button", { name: "Send the review" }).click();
    await h.page.waitForTimeout(2000);
    await h.page.getByText("Review this book").scrollIntoViewIfNeeded().catch(() => {});
    await h.snap({ id: "review-sent", area: A.buy, route: "/shop/<slug>/", state: "after the review was sent: the form is gone; only approved reviews show, so it waits for approval", full: false });
    return "none";
  });

  // ============================================================================================ out of stock
  STEP("sold-out", async () => {
    shell(`from shop.models import Product\nProduct.objects.filter(slug="chemistry-solutions-2027").update(stock=0)`);
    await servers.refresh();
  });
  S("shop-sold-out", A.buy, "/shop/", "one book sold out", "/shop/");
  S("product-sold-out", A.buy, "/shop/chemistry-solutions-2027/", "sold out: be emailed once when it is back", { pattern: "/shop/<slug>/" }, "/shop/chemistry-solutions-2027/");
  S("product-sold-out-in", A.buy, "/shop/chemistry-solutions-2027/", "signed in, sold out: the button that asks for one email", { ...stu, pattern: "/shop/<slug>/" }, "/shop/chemistry-solutions-2027/");
  S("stock-alert", A.buy, "/shop/chemistry-solutions-2027/", "signed in, sold out: the email asked for", { ...stu, vps: ["desktop"], pattern: "/shop/<slug>/" }, async (h) => {
    await h.goto("/shop/chemistry-solutions-2027/");
    await h.page.getByRole("button", { name: "Email me when it is back" }).click();
    await h.page.waitForTimeout(1800);
  });
  S("product-sold-out-asked", A.buy, "/shop/chemistry-solutions-2027/", "signed in, sold out: the page again afterwards (the button is offered again)", { ...stu, pattern: "/shop/<slug>/" }, "/shop/chemistry-solutions-2027/");

  // ============================================================================================ the Django admin (staff)
  const st = { who: "staff" };
  const ids = () => k.state.ids;
  STEP("admin-ids", async () => {
    k.state.ids = pyJson(
      `dict(
        student=User.objects.get(email="atlas-student@example.com").pk, staff=User.objects.get(email="atlas-staff@example.com").pk,
        minor=User.objects.get(email="atlas-minor@example.com").pk, teacher=User.objects.get(email="atlas-teacher@example.com").pk,
        product_papers=Product.objects.get(slug="physics-sample-papers-2027").pk, product_bundle=Product.objects.get(slug="physics-bundle-2027").pk,
        product_solutions=Product.objects.get(slug="chemistry-solutions-2027").pk,
        order_delivered=Order.objects.get(user__email="atlas-student@example.com", status="delivered").pk,
        order_shipped=Order.objects.get(user__email="atlas-student@example.com", status="shipped").pk,
        order_packed=Order.objects.get(user__email="atlas-student@example.com", status="packed").pk,
        order_paid=Order.objects.get(user__email="atlas-student@example.com", status="paid").pk,
        order_pending=Order.objects.filter(user__email="atlas-student@example.com", status="pending").order_by("pk").first().pk,
        number_pending=Order.objects.filter(user__email="atlas-student@example.com", status="pending").order_by("pk").first().number,
        number_delivered=Order.objects.get(user__email="atlas-student@example.com", status="delivered").number,
        number_packed=Order.objects.get(user__email="atlas-student@example.com", status="packed").number,
        review_pending=Review.objects.filter(status="pending").order_by("pk").first().pk,
        quote=(QuoteRequest.objects.order_by("pk").first() or QuoteRequest()).pk,
        quote_number=(QuoteRequest.objects.order_by("pk").first() or QuoteRequest()).number,
        coupon=Coupon.objects.first().pk, offer=Offer.objects.first().pk, collection=Collection.objects.first().pk,
        category=Category.objects.get(slug="sample-papers").pk,
        revision_ready=Revision.objects.get(chapter__subject__code="PHY", chapter__number=1).pk,
        revision_draft=Revision.objects.get(chapter__subject__code="CHE", chapter__number=1).pk,
        clip_failed=Clip.objects.get(processing="failed").pk, clip_ready=Clip.objects.filter(processing="ready").order_by("pk").first().pk,
        chapter=Chapter.objects.get(subject__code="PHY", number=1).pk,
        paper_sample=Paper.objects.get(code="PHY-E01").pk, book=Book.objects.get(slug="physics-2027").pk,
        page_privacy=Page.objects.get(slug="privacy").pk, teacher_profile=TeacherProfile.objects.filter(user__email="atlas-student@example.com").first().pk,
        group_sales=Group.objects.get(name="SALES").pk, group_admin=Group.objects.get(name="ADMIN").pk,
      )`,
      `from accounts.models import User, TeacherProfile
from shop.models import Product, Order, Review, QuoteRequest, Coupon, Offer, Collection, Category
from learn.models import Revision, Clip, Chapter
from content.models import Paper, Book
from pages.models import Page
from django.contrib.auth.models import Group`,
    );
  });
  // a path may hold {name}: the id of a row (STEP admin-ids); the caption shows <id> in its place
  const adminPage = (id, area, path, state, opts = {}) =>
    S(`admin-${id}`, area, path.replace(/\{[^}]+\}/g, "<id>"), state, { ...st, ...opts }, async (h) =>
      h.goto(path.replace(/\{([^}]+)\}/g, (_, key) => ids()[key])),
    );
  const A1 = A.adminDash, A2 = A.adminCatalogue, A3 = A.adminOrders, A4 = A.adminOffers, A5 = A.adminCourse, A6 = A.adminPeople, A7 = A.adminContent, A8 = A.adminSystem;
  // a changelist action, from the list to the form it asks for
  const runAction = async (h, list, rowText, action) => {
    await h.goto(list);
    await h.page.locator("#result_list tbody tr", { hasText: rowText }).first().locator("input.action-select").check();
    await h.page.locator("select[name=action]").selectOption(action);
    await h.page.getByRole("button", { name: "Run" }).click();
    await h.page.waitForLoadState("networkidle");
  };

  adminPage("index", A1, "/admin/", "the ops dashboard: the shop's numbers, what waits, every model of every app");
  adminPage("password-change", A1, "/admin/password_change/", "the admin's change-password page");
  // catalogue
  adminPage("products", A2, "/admin/shop/product/", "the books: price, stock, on sale, with the bulk actions");
  adminPage("product-change", A2, "/admin/shop/product/{product_papers}/change/", "a book: fields, pictures (three), categories, related books");
  adminPage("product-bundle", A2, "/admin/shop/product/{product_bundle}/change/", "a bundle: the books it sells");
  adminPage("product-add", A2, "/admin/shop/product/add/", "a new book");
  adminPage("product-import", A2, "/admin/shop/product/import/", "the import page: a CSV or Excel file of products");
  adminPage("product-export", A2, "/admin/shop/product/export/", "the export page: the format and the fields");
  S("admin-product-import-preview", A2, "/admin/shop/product/import/", "the import page: the exported file read back, what would change", { ...st }, async (h) => {
    await h.goto("/admin/shop/product/export/");
    await h.page.locator("select[name=format]").selectOption({ label: "csv" });
    const [download] = await Promise.all([h.page.waitForEvent("download"), h.page.locator("form input[type=submit], form button[type=submit]").last().click()]);
    const file = path.join(OUT, "products-export.csv");
    await download.saveAs(file);
    await h.goto("/admin/shop/product/import/");
    await h.page.locator("input[type=file]").setInputFiles(file);
    await h.page.locator("select[name=format]").selectOption({ label: "csv" });
    await h.page.locator("form input[type=submit], form button[type=submit]").last().click();
    await h.page.waitForLoadState("networkidle");
  });
  adminPage("categories", A2, "/admin/shop/category/", "the category tree, with its sub-shelves in order");
  adminPage("category-change", A2, "/admin/shop/category/{category}/change/", "a shelf: where it sits in the tree");
  adminPage("collections", A2, "/admin/shop/collection/", "hand-picked collections");
  adminPage("collection-change", A2, "/admin/shop/collection/{collection}/change/", "a collection: its books in order");
  adminPage("producttypes", A2, "/admin/shop/producttype/", "product types and their attributes (none made yet)");
  adminPage("shippingrates", A2, "/admin/shop/shippingrate/", "shipping rates by state");
  // orders and customers
  adminPage("orders", A3, "/admin/shop/order/", "every order, with the filters and the actions");
  adminPage("orders-pending", A3, "/admin/shop/order/?status__exact=pending", "filtered to orders awaiting payment");
  adminPage("order-delivered", A3, "/admin/shop/order/{order_delivered}/change/", "a delivered order: the timeline, the books, payment, shipment, internal notes, invoice");
  adminPage("order-paid", A3, "/admin/shop/order/{order_paid}/change/", "a paid order waiting to be packed");
  adminPage("order-pending", A3, "/admin/shop/order/{order_pending}/change/", "an order awaiting payment");
  S("admin-order-add", A3, "/admin/shop/order/add/", "the staff order form: a phone or school order", { ...st }, async (h) => {
    await h.goto("/admin/shop/order/add/");
    await h.snap({ id: "admin-order-add", route: "/admin/shop/order/add/", state: "the staff order form: a phone or school order, empty" });
    await h.page.locator("input[type=submit]").first().click();
    await h.page.waitForLoadState("networkidle");
    await h.snap({ id: "admin-order-add-error", route: "/admin/shop/order/add/", state: "the staff order form sent without a book or an address" });
    await h.goto("/admin/shop/order/add/");
    await h.fill("#id_email", "atlas-school@example.com");
    await h.fill("#id_discount", "50");
    await h.fill("#id_note", "Phone order from the school office; payment by NEFT.");
    await h.fill("#id_address-name", "Demo Higher Secondary School");
    await h.fill("#id_address-phone", "9864012345");
    await h.fill("#id_address-line1", "School Road");
    await h.fill("#id_address-city", "Guwahati");
    await h.fill("#id_address-district", "Kamrup Metro");
    await h.page.locator("#id_address-state").selectOption("AS");
    await h.fill("#id_address-pin", "781005");
    await h.page.locator("#id_lines-0-product").selectOption({ label: "ExamLeaf Physics Sample Papers + Solutions 2027" }).catch(async () => h.page.locator("#id_lines-0-product").selectOption({ index: 1 }));
    await h.fill("#id_lines-0-quantity", "12");
    await h.page.locator("#id_lines-1-product").selectOption({ index: 3 });
    await h.fill("#id_lines-1-quantity", "6");
    await h.snap({ id: "admin-order-add-filled", route: "/admin/shop/order/add/", state: "the staff order form filled in: two lines, a discount, a note" });
    await h.page.locator("input[type=submit]").first().click();
    await h.page.waitForLoadState("networkidle");
    await h.snap({ id: "admin-order-made", route: "/admin/shop/order/<id>/change/", pattern: "/admin/shop/order/<id>/change/", state: "the staff order made: it waits for a payment link or a payment recorded offline" });
    return "none";
  });
  S("admin-order-action-ship", A3, "/admin/shop/order/", "the action Mark shipped: courier and tracking number for each packed order", { ...st }, async (h) => {
    await runAction(h, "/admin/shop/order/", ids().number_packed, "mark_shipped");
  });
  S("admin-order-action-payment", A3, "/admin/shop/order/", "the action Record a payment received offline (bank transfer, UPI)", { ...st }, async (h) => {
    await runAction(h, "/admin/shop/order/", ids().number_pending, "offline_payment");
  });
  S("admin-order-action-refund", A3, "/admin/shop/order/", "the action Refund in full: the reason, the amount", { ...st }, async (h) => {
    await runAction(h, "/admin/shop/order/", ids().number_delivered, "refund");
  });
  adminPage("customer", A3, "/admin/shop/order/customer/{student}/", "the customer page: the account, orders, addresses, reviews, quotations, alerts, courses");
  adminPage("invoices", A3, "/admin/shop/invoice/", "invoices, each with its PDF");
  adminPage("payments", A3, "/admin/shop/payment/", "payments (read only)");
  adminPage("refunds", A3, "/admin/shop/refund/", "refunds (none yet)");
  adminPage("stockalerts", A3, "/admin/shop/stockalert/", "who waits for which book to be back");
  // offers, reviews, quotations
  adminPage("coupons", A4, "/admin/shop/coupon/", "coupons");
  adminPage("coupon-change", A4, "/admin/shop/coupon/{coupon}/change/", "a coupon: kind, value, limits, validity");
  adminPage("offers", A4, "/admin/shop/offer/", "automatic offers");
  adminPage("offer-change", A4, "/admin/shop/offer/{offer}/change/", "an offer: what it covers, its minimum, how it combines");
  adminPage("reviews", A4, "/admin/shop/review/", "reviews to moderate, with Approve and Reject");
  adminPage("reviews-pending", A4, "/admin/shop/review/?status__exact=pending", "filtered to reviews waiting for approval");
  adminPage("review-change", A4, "/admin/shop/review/{review_pending}/change/", "a review: the buyer's words, the status to set");
  adminPage("quotes", A4, "/admin/shop/quoterequest/", "school and bulk quotation requests");
  S("admin-quote-made", A4, "/admin/shop/quoterequest/<id>/change/", "a request after the action Make the quotation PDF: the file, valid 15 days", { ...st, pattern: "/admin/shop/quoterequest/<id>/change/" }, async (h) => {
    await runAction(h, "/admin/shop/quoterequest/", ids().quote_number, "make_quotation");
    await h.snap({ id: "admin-quote-action", route: "/admin/shop/quoterequest/", state: "the list after the action Make the quotation PDF: the message and the PDF link" });
    await h.goto(`/admin/shop/quoterequest/${ids().quote}/change/`);
    await h.snap({ id: "admin-quote-change", route: "/admin/shop/quoterequest/<id>/change/", pattern: "/admin/shop/quoterequest/<id>/change/", state: "a quotation request: the books asked for, the discount and shipping, the quotation PDF" });
    return "none";
  });
  // the revision course
  adminPage("chapters", A5, "/admin/learn/chapter/", "chapters with their marks and whether a revision exists");
  adminPage("chapter-change", A5, "/admin/learn/chapter/{chapter}/change/", "a chapter: marks, frequency, must-do, flash cards");
  adminPage("revisions", A5, "/admin/learn/revision/", "revisions with the number of clips; Publish and Back to draft");
  adminPage("revision-change", A5, "/admin/learn/revision/{revision_ready}/change/", "a published revision with its clips and their processing status");
  adminPage("revision-draft", A5, "/admin/learn/revision/{revision_draft}/change/", "a draft revision whose clips are waiting, processing and failed");
  adminPage("clips", A5, "/admin/learn/clip/", "clips with their processing status (uploaded, processing, ready, failed)");
  adminPage("clips-failed", A5, "/admin/learn/clip/?processing__exact=failed", "filtered to clips that failed to process");
  adminPage("clip-change", A5, "/admin/learn/clip/{clip_failed}/change/", "a clip that failed: the error and Process the video again");
  adminPage("bookcodes", A5, "/admin/learn/bookcode/", "book codes: made by the command, only their hashes kept; one redeemed");
  adminPage("entitlements", A5, "/admin/learn/entitlement/", "who has which subject open, and how they got it");
  adminPage("quizitems", A5, "/admin/learn/quizitem/", "one-mark quiz items made from the papers");
  adminPage("flashcards", A5, "/admin/learn/flashcard/", "flash cards");
  // people and roles
  adminPage("users", A6, "/admin/accounts/user/", "users: class, board, district, under 18; filter by role");
  adminPage("users-sales", A6, "/admin/accounts/user/?groups__id__exact={group_sales}", "filtered to the role SALES");
  adminPage("user-student", A6, "/admin/accounts/user/{student}/change/", "a student: details, parent, log-in by SMS, roles and permissions");
  adminPage("user-staff", A6, "/admin/accounts/user/{staff}/change/", "a staff member: is_staff, is_superuser, the role ADMIN");
  adminPage("user-add", A6, "/admin/accounts/user/add/", "a new user");
  adminPage("groups", A6, "/admin/auth/group/", "roles (groups); ExamLeaf's bootstrap_roles sets their permissions");
  adminPage("group-change", A6, "/admin/auth/group/{group_sales}/change/", "a role: the permissions it holds");
  adminPage("teachers", A6, "/admin/accounts/teacherprofile/", "teacher access asked for, with Verify and Revoke");
  adminPage("teacher-change", A6, "/admin/accounts/teacherprofile/{teacher_profile}/change/", "a teacher request: the school, the note on how it was checked");
  adminPage("consents", A6, "/admin/accounts/consentrecord/", "consent records (read only)");
  adminPage("deletions", A6, "/admin/accounts/deletionrequest/", "account deletion requests (none)");
  adminPage("sessions", A6, "/admin/usersessions/usersession/", "signed-in devices");
  adminPage("emails", A6, "/admin/account/emailaddress/", "email addresses and whether they are confirmed");
  // papers and pages
  adminPage("books", A7, "/admin/content/book/", "books");
  adminPage("papers", A7, "/admin/content/paper/", "papers: published, open sample");
  adminPage("paper-change", A7, "/admin/content/paper/{paper_sample}/change/", "a paper: its marks, time and the open-sample switch");
  adminPage("questions", A7, "/admin/content/question/", "questions");
  adminPage("pages", A7, "/admin/pages/page/", "the legal pages, with [placeholders] still to fill in");
  adminPage("page-change", A7, "/admin/pages/page/{page_privacy}/change/", "a legal page: its text and version");
  adminPage("attempts", A7, "/admin/practice/attempt/", "the marks students saved");
  // system
  adminPage("periodic-tasks", A8, "/admin/django_celery_beat/periodictask/", "the daily and hourly tasks");
  adminPage("task-results", A8, "/admin/django_celery_results/taskresult/", "what the background tasks did");
  adminPage("sms-log", A8, "/admin/ops/smslog/", "SMS sent (none without a gateway)");
  adminPage("suppressions", A8, "/admin/ops/emailsuppression/", "addresses that bounced");
  adminPage("axes", A8, "/admin/axes/accessattempt/", "failed log-in attempts (django-axes)");
  adminPage("authenticators", A8, "/admin/mfa/authenticator/", "second factors: the staff's authenticator apps");
  adminPage("theme", A8, "/admin/admin_interface/theme/", "the admin's theme");
  adminPage("tags", A8, "/admin/taggit/tag/", "tags of questions and clips");

  // Django's own pages outside the admin
  S("clip-preview", A.django, "/learn/preview/<clip>/", "staff: the player for a clip, on the admin's layout", { ...st, pattern: "/learn/preview/<clip>/" }, async (h) => h.goto(`/learn/preview/${ids().clip_ready}/`));
  S("api-docs", A.django, "/api/docs/", "the API's Swagger page", { ...st }, "/api/docs/");
  S("api-redoc", A.django, "/api/redoc/", "the API's Redoc page", { ...st }, "/api/redoc/");
  S("django-404", A.django, "/admin/no-such-page/", "Django's own 404 (under /admin/)", { ...st }, "/admin/no-such-page/");

  // ============================================================================================ G. System
  S("404", A.system, "/this-page-does-not-exist/", "a page that does not exist (the books are offered)", "/this-page-does-not-exist/");
  S("robots", A.system, "/robots.txt", "what crawlers are told", "/robots.txt");
  S("sitemap", A.system, "/sitemap.xml", "the fixed pages, books and products", "/sitemap.xml");
  S("manifest", A.system, "/manifest.webmanifest", "the web app manifest", "/manifest.webmanifest");

  // ============================================================================================ without Django, without a connection
  STEP("outage-start", async () => servers.outage());
  S("outage-shop", A.system, "/shop/", "Django cannot be reached: a public page says so and offers Try again", "/shop/");
  S("outage-book", A.system, "/books/physics-2027/", "Django cannot be reached: a book page", { pattern: "/books/<slug>/" }, "/books/physics-2027/");
  S("outage-solutions", A.system, "/s/PHY-E01/", "Django cannot be reached: the solutions of a paper", { pattern: "/s/<code>/" }, "/s/PHY-E01/");
  S("outage-account", A.system, "/account/", "Django cannot be reached: a signed-in page answers 503 with a page of its own", { who: "student" }, "/account/");
  STEP("outage-end", async () => servers.recover());
  S("offline-real", A.system, "/offline/", "the browser has no connection: the service worker answers a page it does not hold with the offline page", async (h) => {
    await h.goto("/");
    await h.page.evaluate(() => navigator.serviceWorker.ready);
    await h.page.waitForFunction(() => Boolean(navigator.serviceWorker.controller), null, { timeout: 20000 });
    await h.ctx.setOffline(true);
    await h.page.goto(`${BASE}/shop/`).catch(() => {});
    await h.page.waitForTimeout(800);
  });

  // ============================================================================================ clean-up
  // the temporary accounts and what they made go only when asked (--cleanup), so that scenes can be run again
  STEP("cleanup", async () => {
    if (!k.flag("cleanup")) return console.log("  (kept: pass --cleanup to delete the temporary accounts)");
    seed("cleanup");
  });

  async function settleQuiet(h) {
    await h.page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  }
}

register({ flag, S, STEP, AREAS, creds, shell, pyJson, seed, manage, emailed, CODE, logLength, sleep, servers, login, ensureLogin, freshTotp, totp, BASE, OUT, DJANGO_ENV, PY, WEB, listening, DJANGO_PORT, newContext, settle, snap, statePath, fs, path, captures });

// ---------------------------------------------------------------------------------------------------- run
/** `--fresh`: a new SQLite database with everything the pages need (README of examleaf-web, "Set up and run"). */
function freshDatabase() {
  const url = DJANGO_ENV.DATABASE_URL ?? "";
  const file = /^sqlite:\/\/\/?(\/[^?]*)/.exec(url)?.[1];
  if (!file) throw new Error("--fresh needs DATABASE_URL=sqlite:////absolute/path/db.sqlite3 in the backend environment");
  servers.stop("django");
  for (const suffix of ["", "-journal", "-wal", "-shm"]) fs.rmSync(file + suffix, { force: true });
  for (const args of [
    ["migrate", "--noinput"],
    ["bootstrap_roles"],
    ["import_papers", "--all", "--fixtures"],
    ["import_chapter_insights", "--fixtures"],
    ["build_quiz_items"],
    ["seed_shop", "--stock", "100"],
    ["collectstatic", "--noinput"],
  ]) {
    log(`manage.py ${args.join(" ")}`);
    manage(...args);
  }
}

async function main() {
  if (flag("fresh")) freshDatabase();
  if (flag("list")) {
    for (const scene of scenes) console.log(scene.kind === "step" ? `step   ${scene.id}` : `scene  ${scene.id.padEnd(34)} ${scene.area}  ${scene.route}  [${scene.state}]`);
    return;
  }
  const started = Date.now();
  await servers.startDjango();
  await servers.startFrontend();
  browser = await chromium.launch();
  // new passwords (seed base) end the sessions kept in the state files
  if (!ONLY || ONLY.test("prepare")) for (const who of ["student", "staff"]) fs.rmSync(statePath(who), { force: true });
  // a partial run (--only) is merged into the manifest of the runs before it, scene by scene
  const manifestFile = path.join(OUT, "manifest.json");
  const before = ONLY && fs.existsSync(manifestFile) ? JSON.parse(fs.readFileSync(manifestFile, "utf8")) : null;
  if (before) counter = Math.max(0, ...before.captures.map((row) => row.seq ?? 0));
  const ran = new Set();
  for (const [position, scene] of scenes.entries()) {
    if (ONLY && !ONLY.test(scene.id)) continue;
    ran.add(scene.id);
    if (scene.kind === "step") {
      log(`step ${scene.id}`);
      try {
        await scene.run({ shell, pyJson, seed, manage, servers, sleep, creds, log });
      } catch (error) {
        failures.push({ id: scene.id, step: true, error: String(error).slice(0, 1500) });
        console.error(`  STEP FAILED ${scene.id}: ${String(error).slice(0, 1500)}`);
      }
      continue;
    }
    const who = scene.options.who ?? "anon";
    if (who !== "anon") await ensureLogin(who);
    const vps = scene.options.vps ?? ["desktop", "phone"];
    for (const vp of vps) {
      log(`${scene.id} (${vp})`);
      const ctx = await newContext(vp, who, scene.options.context ?? {});
      const page = await ctx.newPage();
      const problems = [];
      page.on("pageerror", (error) => problems.push(`pageerror: ${String(error).slice(0, 160)}`));
      page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && problems.push(`console: ${m.text().slice(0, 160)}`));
      page.on("requestfailed", (r) => {
        const aborted = /ERR_ABORTED/.test(r.failure()?.errorText ?? "") || /_rsc=/.test(r.url()); // prefetches cut short by a click
        if (!aborted) problems.push(`failed: ${r.url().replace(BASE, "").slice(0, 100)}`);
      });
      const before = captures.length;
      const h = helpers(page, ctx, vp, { ...scene, scene_id: scene.id, order: position, who: who === "anon" ? "anonymous" : who === "student" ? "student" : "staff" });
      try {
        const over = (await scene.run(h)) ?? {};
        if (over !== "none" && captures.length === before) {
          await snap(page, { ...scene, scene_id: scene.id, order: position, ...scene.options, ...over, vp, status: h.status, who: who === "anon" ? "anonymous" : who });
        }
        for (const row of captures.slice(before)) if (problems.length) row.problems = problems.slice(0, 5);
      } catch (error) {
        failures.push({ id: scene.id, viewport: vp, url: page.url().replace(BASE, ""), error: String(error).slice(0, 500) });
        console.error(`  FAILED ${scene.id} (${vp}): ${String(error).slice(0, 300)}`);
        await page.screenshot({ path: path.join(OUT, `failed-${scene.id}-${vp}.png`) }).catch(() => {});
      } finally {
        await ctx.close();
      }
    }
  }
  await browser.close();
  const meta = {
    made: new Date().toISOString(),
    base: BASE,
    commit: (() => {
      try {
        return execFileSync("git", ["-C", REPO, "rev-parse", "HEAD"]).toString().trim();
      } catch {
        return null;
      }
    })(),
    // what the backend ran with (no secret: nothing whose name says secret, key, token, password or database)
    backend_env: Object.fromEntries(Object.entries(ENV_FILE ? readEnvFile(ENV_FILE) : {}).filter(([name]) => !/SECRET|KEY|TOKEN|PASSWORD|DATABASE/.test(name))),
    viewports: Object.fromEntries(Object.entries(VIEWPORTS).map(([k, v]) => [k, { width: v.options.viewport.width, height: v.options.viewport.height, dpr: v.options.deviceScaleFactor }])),
    seconds: Math.round((Date.now() - started) / 1000),
  };
  const merged = before
    ? {
        captures: [...before.captures.filter((row) => !ran.has(row.scene)), ...captures],
        failures: [...before.failures.filter((f) => !ran.has(f.id)), ...failures],
      }
    : { captures, failures };
  fs.writeFileSync(manifestFile, JSON.stringify({ meta: before ? { ...before.meta, updated: meta.made } : meta, areas: AREAS, ...merged }, null, 1));
  log(`${captures.length} captures this run, ${merged.captures.length} in all, ${merged.failures.length} failures -> ${manifestFile}`);
}
await main();
