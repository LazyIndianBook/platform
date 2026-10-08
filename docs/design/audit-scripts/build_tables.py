"""Builds the table sections of coverage-matrix.md from the live data. Prints markdown to stdout (sections), and writes
counts.json. The prose sections (journeys, gaps, generic) are written by hand in the final document template."""
import collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matrix_data as M

SCR = os.path.dirname(os.path.abspath(__file__))
urls = json.load(open(f"{SCR}/urls-clean.json"))
first = {(r["route"], r["name"]) for r in json.load(open(f"{SCR}/urls-clean.first.json"))}
probe = json.load(open(f"{SCR}/probe-results.json"))
schema = json.load(open(f"{SCR}/schema.json"))
tpl = json.load(open(f"{SCR}/tpl-scan.json"))

# ---------------------------------------------------------------------------------------------------------------------
def kind_of(route, view):
    if route.startswith("admin"):
        return "admin"
    if route.startswith("^__debug__"):
        return "dev"
    if route.startswith("_allauth/"):
        return "headless"
    if route.startswith("api/"):
        return "api"
    return "site"

groups = collections.defaultdict(list)
for u in urls:
    groups[kind_of(u["route"], u["view"])].append(u)

# baseline chrome per persona (classes the header and footer bring to every page)
base = {}
for r in probe:
    if r["path"] == "/about/" and r["method"] == "GET" and "vocab" in r:
        base[r["persona"]] = set(r["vocab"])

def redesign(pp, override=None, library=False):
    """done: own use of the vocabulary (3 or more classes, or 2 on a short site-owned page). done via allauth elements:
    the library's page, its controls drawn by templates/allauth/elements. partial: 1 class, or a pre-redesign class name
    left. layout only: new header, footer and card, nothing of the vocabulary in the page. n/a: not an HTML page."""
    if override:
        return override
    if not pp:
        return "n/a"
    persona, path = pp
    for r in probe:
        if r["persona"] == persona and r["path"] == path and r["method"] == "GET" and r.get("key") and "vocab" in r and not r["key"].startswith(("order status", "order link status", "done status")) and r["status"] in (200, 400, 401):
            own = set(r["vocab"]) - base.get(persona, base["student"])
            if r["legacy"]:
                return "partial"
            if library:
                return "done via allauth elements" if len(own) >= 2 else ("partial" if own else "layout")
            if len(own) >= 3 or (len(own) == 2 and r["bytes"] < 14000):
                return "done"
            return "partial" if own else "layout"
    return "n/a"

REDESIGN_LABEL = {"done": "done", "done via allauth elements": "done via allauth elements", "partial": "partial", "layout": "layout only", "none": "not restyled", "n/a": "n/a", "unverified": "unverified (not rendered by the probe)"}

# ---------------------------------------------------------------------------------------------------------------------
def esc(s):
    return s.replace("|", "\\|")

def row(cells):
    return "| " + " | ".join(esc(c) for c in cells) + " |"

site_keys = {}
for r in M.SITE:
    site_keys[r["k"]] = r
    for extra in r.get("also", []):
        site_keys[extra] = r
site_rows_by_sec = collections.OrderedDict()
unannotated, matched_routes = [], collections.Counter()
allauth_by_name = {}
for u in groups["site"]:
    route, name, view = u["route"], u["name"], u["view"]
    if route in site_keys:
        matched_routes[site_keys[route]["k"]] += 1
        continue
    short = name.split(":")[-1]
    if view.startswith(("allauth.",)) and name in M.ALLAUTH:
        allauth_by_name[name] = u
        continue
    if name in ("google_callback", "google_login_by_token"):
        continue
    if route in M.REDIRECTS or route.startswith("account/social/"):
        continue
    unannotated.append((route, name, view))

for sec in sorted({r.get("sec") for r in M.SITE if r.get("sec")}):
    pass
order = {}
current = None
for r in M.SITE:
    if r.get("sec"):
        current = r["sec"]
    order.setdefault(current, []).append(r)
sections = collections.OrderedDict(sorted(order.items(), key=lambda kv: kv[0]))

HEAD = ["Route", "Purpose", "Who may use it", "Template / serializer", "States", "Journey", "Status", "Redesign"]
counts = {"redesign": collections.Counter(), "aud": collections.Counter(), "aud_allauth": collections.Counter(), "rows": 0}
out = []

def add_site_row(r):
    rd = redesign(r.get("pp"), r.get("rd"))
    if r["kind"] in ("action", "file", "redirect", "json") and not r.get("rd"):
        rd = "n/a"
    n = 1 + len(r.get("also", []))
    if r["kind"] == "page" and r["a"] != "dev" and r["k"] != "admin/":
        counts["redesign"][rd] += n
    if r["a"] != "dev" and r["k"] != "admin/":  # admin/ stands for the 382 admin patterns, counted on their own
        counts["aud"][r["a"]] += n
    text = r["p"] + (f". {r['note']}" if r.get("note") else "")
    out.append(row([r["r"], text, r["w"], r["t"], r["s"], r["j"], r["st"], REDESIGN_LABEL.get(rd, rd)]))

sec_title = {
    "A": "A. Discover: pages anyone can read", "B": "B. Buy: shop, cart, checkout", "C": "C. After the order",
    "D": "D. Record: marks and progress", "E": "E. Account and data rights", "F": "F. Sign-in and recovery (allauth, restyled in part)",
    "G": "G. Staff", "H": "H. System and machine endpoints", "I": "I. Development only",
}
SECTION_BODY = {}
for title, rows in sections.items():
    letter = title[0]
    out.clear()
    out.append(row(HEAD)); out.append("|" + "---|" * len(HEAD))
    for r in rows:
        add_site_row(r)
    SECTION_BODY[letter] = "\n".join(out)

# F: allauth
out.clear(); out.append(row(HEAD)); out.append("|" + "---|" * len(HEAD))
f_counts = collections.Counter()
for name, a in M.ALLAUTH.items():
    library = a["t"].startswith("allauth")
    rd = redesign(a.get("pp"), None, library)
    if a.get("pp") is None:  # a stage or a factor the probe cannot reach: judged from the template
        rd = {"account_email_verification_sent": "done", "account_confirm_login_code": "done", "account_verify_phone": "done", "mfa_authenticate": "done", "socialaccount_signup": "done", "mfa_login_webauthn": "n/a", "mfa_download_recovery_codes": "n/a", "google_login": "n/a"}.get(name, "unverified")
    f_counts[rd] += 1
    counts["redesign"][rd] += (1 + len(a.get("also", []))) if rd != "n/a" else 0
    a_aud = "anon" if a["w"].startswith(("anonymous", "a visitor", "the visitor", "holder", "anyone")) else "student"
    counts["aud_allauth"][a_aud] += 1 + len(a.get("also", []))
    journey = "J2 sign-in" if not name.startswith(("mfa_",)) or name in ("mfa_authenticate", "mfa_login_webauthn") else "J2 sign-in, J3 account"
    if name in ("account_email", "account_change_password", "account_set_password", "account_change_phone", "account_verify_phone", "socialaccount_connections", "account_reauthenticate"):
        journey = "J3 account"
    out.append(row([a["r"], a["p"], a["w"], a["t"], a["s"], journey, a["st"], REDESIGN_LABEL.get(rd, rd)]))
redir_rows = ["| `/account/register/` and `/account/social/...` (5 routes) | Redirects to `/account/signup/` (query kept) and to the `/account/3rdparty/...` pages | anyone | `RedirectView` | n/a | J2 sign-in | existing | n/a |"]
SECTION_BODY["F"] = "\n".join(out + redir_rows)
counts["aud_allauth"]["anon"] += 5  # the five redirects

# counts of unmatched site routes
matched = sum(matched_routes.values())
counts["site_patterns"] = len(groups["site"])

# ---------------------------------------------------------------------------------------------------------------------
# staff: admin by role
adm = collections.defaultdict(dict)
for r in probe:
    m = re.match(r"admin (\S+) (changelist|add)$", r.get("key", ""))
    if m:
        adm[m.group(1)].setdefault(r["persona"], {})[m.group(2)] = r["status"]
ROLE = [("admin", "ADMIN"), ("editor", "CONTENT_EDITOR"), ("sales", "SALES"), ("support", "SUPPORT")]
ACTIONS = {
    "shop.product": "Put on sale, Take off sale, Set stock",
    "shop.order": "Mark packed, delivered, shipped (courier and tracking), Cancel, Refund in full, Email payment link, Record offline payment; Add order (phone or school order); customer page",
    "shop.review": "Approve, Reject", "shop.quoterequest": "Make the quotation PDF (download link)",
    "accounts.teacherprofile": "Verify (gives TEACHER), Revoke", "learn.revision": "Publish, Back to draft",
    "learn.clip": "Move up, Move down, Process the video again; Preview link", "accounts.user": "CSV export (ADMIN)",
    "accounts.consentrecord": "CSV export (ADMIN)", "practice.attempt": "CSV export (ADMIN)",
}
def cell(d):
    if not d:
        return "-"
    cl, ad = d.get("changelist"), d.get("add")
    if cl == 200 and ad == 200:
        return "view + add"
    if cl == 200:
        return "view"
    return "no"
adm_rows = [row(["Model (app.model)", "ADMIN", "CONTENT_EDITOR", "SALES", "SUPPORT", "Staff actions beyond edit"]), "|---|---|---|---|---|---|"]
for model in sorted(adm):
    cells = [cell(adm[model].get(p)) for p, _ in ROLE]
    adm_rows.append(row([f"`{model}`", *cells, ACTIONS.get(model, "")]))
ADMIN_TABLE = "\n".join(adm_rows)
counts["admin_models"] = len(adm)
counts["admin_patterns"] = len(groups["admin"])

# ---------------------------------------------------------------------------------------------------------------------
# API v1 from the schema
probe_api = collections.defaultdict(dict)
for r in probe:
    if r.get("api"):
        probe_api[(r["method"], r["path"])][r["persona"]] = r["status"]
def norm(path):
    return re.sub(r"\{[^}]+\}", "X", path)
probe_norm = collections.defaultdict(dict)
for (m, p), d in probe_api.items():
    for k, v in d.items():
        probe_norm[(m, norm(re.sub(r"/(EL-[\d-]+|PHY-E01|physics-2027|physics-sample-papers-2027|class-12-books|exam-week|privacy|[\w-]{20,}|\d+)(?=/|$)", "/X", p).split("?")[0]))][k] = v
JOURNEY = {"auth": "J2 sign-in", "account": "J3 account, data rights", "catalogue": "J1 discover, access", "shop": "J1 buy", "record": "J1 access, revise", "learn": "J1 revise", "site": "J1 discover"}
THROTTLED = ("auth/", "orders/lookup", "cart/coupon", "learn/redeem", "attempt/", "payment", "quotes", "stock-alert", "reviews", "me/export", "me/deletion", "me/parent-consent")
api_rows = [row(["Path (`/api/v1`)", "Methods", "Purpose", "Who (probe: anonymous / student)", "Request → response serializer", "States", "Journey", "Status"]), "|---|---|---|---|---|---|---|---|"]
paths = collections.OrderedDict()
for path, item in schema["paths"].items():
    for method, op in item.items():
        if method in ("get", "post", "put", "patch", "delete"):
            paths.setdefault(path, []).append((method.upper(), op))
new_api = {u["route"] for u in groups["api"] if (u["route"], u["name"]) not in first}
def api_new(path):
    key = norm(path).replace("/api/v1", "")
    return any(norm(re.sub(r"\^|\$|\(\?P<[^>]+>[^)]+\)", "X", n.replace("api/^(?P<version>v1)/", ""))).strip("/").replace("//", "/") == key.strip("/") for n in new_api) or any(key.strip("/").split("/")[0] in n.replace("api/^(?P<version>v1)/", "") and key.strip("/") in re.sub(r"<[^>]+>|\(\?P<[^>]+>[^)]+\)|\^|\$", "X", n.replace("api/^(?P<version>v1)/", "")).strip("/") for n in new_api)
NEW_API_PATHS = {"/api/v1/auth/exchange/", "/api/v1/config/", "/api/v1/me/parent-consent/", "/api/v1/me/teacher/", "/api/v1/orders/t/{token}/", "/api/v1/pages/", "/api/v1/pages/{slug}/", "/api/v1/products/{slug}/reviews/", "/api/v1/products/{slug}/stock-alert/", "/api/v1/quotes/"}
def first_sentence(text):
    text = re.sub(r"\s+", " ", (text or "").strip())
    m = re.match(r"(.{20,260}?\.)(\s|$)", text)
    return m.group(1) if m else text[:230]
n_ops = 0
for path, ops in paths.items():
    methods = sorted({m for m, _ in ops}, key=["GET", "POST", "PUT", "PATCH", "DELETE"].index)
    n_ops += len(ops)
    desc = first_sentence(next((op.get("description") or op.get("summary") for m, op in ops if op.get("description") or op.get("summary")), ""))
    desc = desc or {"/api/v1/boards/": "The exam boards.", "/api/v1/boards/{id}/": "One board.", "/api/v1/subjects/": "Subjects with their board and class; filter by board.",
                    "/api/v1/subjects/{id}/": "One subject.", "/api/v1/papers/": "Published papers; filter by book, subject, tier; search by code or title.", "/api/v1/papers/{code}/": "One published paper (its solutions are a separate path)."}.get(path, "")
    tag = (ops[0][1].get("tags") or ["site"])[0]
    reqs, resps = set(), set()
    for m, op in ops:
        rq = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "").split("/")[-1]
        if rq:
            reqs.add(rq.replace("Request", "").replace("Patched", ""))
        for code, rs in op.get("responses", {}).items():
            sch = rs.get("content", {}).get("application/json", {}).get("schema", {})
            ref = sch.get("$ref") or (sch.get("items", {}) or {}).get("$ref") or ""
            if ref and code.startswith("2"):
                resps.add(ref.split("/")[-1])
    nothing = "PDF file" if ("invoice" in path or "credit-notes" in path) else ("JSON, the website's export" if path.endswith("/export/") else "inline JSON (no serializer in the schema)")
    ser = f"{', '.join(sorted(reqs)) or 'none'} → {', '.join(sorted(resps)) or nothing}"
    pn = {}
    for m in methods:
        d = probe_norm.get((m, norm(path)), {})
        for k, v in d.items():
            pn.setdefault(k, []).append(f"{m} {v}")
    who = " / ".join((", ".join(pn.get(k, [])) or "-") for k in ("anon", "student"))
    anon_codes = {int(x.split()[1]) for x in pn.get("anon", [])}
    student_codes = {int(x.split()[1]) for x in pn.get("student", [])}
    public = bool(anon_codes) and not anon_codes <= {401, 403}
    states = ["D"]
    if any(op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "").split("/")[-1].startswith("Paginated") for m, op in ops):
        states.append("E")
    if any(m in ("POST", "PUT", "PATCH") for m in methods):
        states.append("V")
    if not public or 401 in anon_codes or 403 in student_codes:
        states += ["P", "S"]
    if any(t in path for t in THROTTLED) or "payment" in path:
        states.append("U")
    who_text = ("anyone" if public and not (401 in anon_codes and len(anon_codes) == 1) else "signed in, email confirmed") if True else ""
    if path.startswith("/api/v1/learn/") and tag == "learn" and path not in ("/api/v1/learn/chapters/", "/api/v1/learn/chapters/{id}/"):
        who_text = "signed in; the subject must be unlocked with a book code (403 otherwise)"
    if path in ("/api/v1/papers/{code}/solutions/",):
        who_text = "signed in, email confirmed (anyone when `SOLUTIONS_REQUIRE_LOGIN=0`)"
    if path in ("/api/v1/auth/password/change/", "/api/v1/me/export/", "/api/v1/me/deletion/"):
        who_text = "signed in; the password is asked again"
    if path == "/api/v1/orders/t/{token}/":
        who_text = "whoever holds the emailed link"
    SPECIAL = {"/api/v1/auth/token/refresh/": "holder of a refresh token", "/api/v1/auth/logout/": "holder of a refresh token (it is sent in the body)", "/api/v1/auth/token/verify/": "anyone with a token to check",
               "/api/v1/auth/exchange/": "an app signed in through the headless API (its session is exchanged)", "/api/v1/config/": "anyone", "/api/v1/pages/": "anyone", "/api/v1/pages/{slug}/": "anyone",
               "/api/v1/quotes/": "anyone (Turnstile token when keys are set)", "/api/v1/products/{slug}/stock-alert/": "anyone (rate limited)", "/api/v1/products/{slug}/reviews/": "anyone to read; a buyer, signed in, to write"}
    if path in SPECIAL:
        who_text = SPECIAL[path]
    status = "existing" if path not in NEW_API_PATHS else "in progress (not in the last commit)"
    api_rows.append(row([f"`{path.replace('/api/v1', '') or '/'}`", ", ".join(methods), desc, f"{who_text}. Probe: {who}", ser, " ".join(states), JOURNEY.get(tag, "J1"), status]))
API_TABLE = "\n".join(api_rows)
counts["api_paths"] = len(paths)
counts["api_ops"] = n_ops
counts["api_patterns"] = len(groups["api"])
counts["headless"] = len(groups["headless"])

# headless
HL = {
    "account:login": "Log in with email or mobile number and password", "account:signup": "Register", "account:verify_email": "Confirm the email code (GET shows what is pending)",
    "account:resend_email_verification_code": "Send the email code again", "account:request_login_code": "Ask for a log-in code (email or SMS)", "account:confirm_login_code": "Confirm the log-in code",
    "account:resend_login_code": "Send the log-in code again", "account:request_password_reset": "Ask for a password reset email", "account:reset_password": "Set a new password from the emailed key",
    "account:reauthenticate": "Enter the password again", "account:current_session": "Read the session (GET) or log out (DELETE)", "account:manage_email": "List, add, change and remove email addresses",
    "account:manage_phone": "Read and change the mobile number", "account:change_password": "Change the password", "account:verify_phone": "Confirm the texted code",
    "account:resend_phone_verification_code": "Send the texted code again", "mfa:authenticate": "Second step at log-in", "mfa:reauthenticate": "Second step before a sensitive change",
    "mfa:authenticators": "List the second factors", "mfa:manage_totp": "Set up or remove the authenticator app", "mfa:manage_recovery_codes": "See or regenerate recovery codes",
    "mfa:manage_webauthn": "List, add, rename and remove passkeys", "mfa:login_webauthn": "Log in with a passkey", "mfa:authenticate_webauthn": "Passkey as the second step",
    "mfa:reauthenticate_webauthn": "Passkey to re-check", "socialaccount:redirect_to_provider": "Start Google sign-in", "socialaccount:provider_token": "Sign in with a Google token (the app)",
    "socialaccount:provider_signup": "Finish the sign-up after Google", "socialaccount:manage_providers": "List and disconnect connected providers", "config": "What this server offers (flows, providers)",
    "tokens:refresh": "Refresh the session token (app client)", "openapi_json": "The OpenAPI document", "openapi_yaml": "The OpenAPI document (YAML)",
}
hl_rows = collections.OrderedDict()
for u in groups["headless"]:
    if not u["name"]:  # a second, unnamed pattern for a path that has a named one
        continue
    n = u["name"].replace("headless:", "")
    client = "app" if n.startswith("app:") else "browser" if n.startswith("browser:") else "both"
    key = re.sub(r"^(app|browser):", "", n)
    hl_rows.setdefault(key, {"routes": [], "clients": set()})
    hl_rows[key]["routes"].append(u["route"]); hl_rows[key]["clients"].add(client)
hl = [row(["Name (`headless:<client>:...`)", "Path under `/_allauth/<app or browser>/v1/`", "Purpose", "Clients"]), "|---|---|---|---|"]
for key, d in hl_rows.items():
    p = sorted(d["routes"])[0]
    p = re.sub(r"^_allauth/(app|browser)/v1/", "", p)
    hl.append(row([f"`{key}`", f"`/{p}`", HL.get(key, "allauth.headless"), "app, browser" if len(d["clients"]) > 1 else ", ".join(d["clients"])]))
HEADLESS_TABLE = "\n".join(hl)
counts["headless_names"] = len(hl_rows)

counts["allauth_redesign"] = dict(f_counts)
counts["unannotated"] = unannotated
counts["groups"] = {k: len(v) for k, v in groups.items()}
counts["redesign"] = dict(counts["redesign"])
counts["aud"] = dict(counts["aud"])
counts["aud_allauth"] = dict(counts["aud_allauth"])
counts["new_routes_since_start"] = sorted(r for r in {(u["route"], u["name"]) for u in urls} - first)[:5]
json.dump({k: v for k, v in counts.items()}, open(f"{SCR}/counts.json", "w"), indent=1, default=list)
json.dump({"SECTIONS": SECTION_BODY, "ADMIN": ADMIN_TABLE, "API": API_TABLE, "HEADLESS": HEADLESS_TABLE, "sec_title": sec_title}, open(f"{SCR}/tables.json", "w"), indent=1)
print(json.dumps({k: v for k, v in counts.items()}, indent=1, default=list))
