"""CI's dependency report: pip-audit's JSON and npm audit's JSON (one per Next.js app) made into one file, which the
deploy loads into the private storage (manage.py load_dependency_report) for the console's System page: the open
advisories by severity, each with its package, version, fix and link; the versions that matter (Django, Next.js).

    python scripts/dependency_report.py --pip pip-audit.json --npm frontend=npm-frontend.json \
        --npm admin=npm-admin.json --commit "$GITHUB_SHA" --output dependency-report.json

A missing or unreadable input, or one that is no audit's output (npm audit writes {"message", "error"} when it could
not ask the registry), is reported in the file (`inputs`: `ok` false), never a failure: the report says what it saw.
With --strict the file is written all the same, and the exit status is 1 when any input is not ok: CI uses it, so that
an audit that did not run makes no artifact to be loaded, instead of a report that looks clean."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SEVERITIES = {"critical", "high", "moderate", "low"}


def read(path):
    try:
        return json.loads(Path(path).read_text() or "null"), ""
    except (OSError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"[:200]


def unusable(data, key):
    """Why an audit's output is no audit, or "": pip-audit and npm audit always write `key` (a list of dependencies,
    a map of vulnerabilities), even for a clean tree; an empty file, or npm's error object, did not run."""
    if isinstance(data, list) or (isinstance(data, dict) and key in data):
        return ""
    message = str(data.get("message") or "") if isinstance(data, dict) else ""
    return f"No '{key}' in it" + (f": {message}" if message else "")[:200]


def pip_rows(data):
    """pip-audit's `--format json`: {"dependencies": [{"name", "version", "vulns": [{"id", "fix_versions", …}]}]}.
    PyPI's advisories carry no severity: "unknown", the page says so."""
    rows, versions = [], {}
    dependencies = data.get("dependencies", []) if isinstance(data, dict) else data or []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        name, version = str(dependency.get("name", "")), str(dependency.get("version", ""))
        if name.lower() == "django":
            versions["django"] = version
        for vuln in dependency.get("vulns") or []:
            identifier = str(vuln.get("id", ""))
            rows.append(
                {
                    "id": identifier,
                    "ecosystem": "pypi",
                    "project": "examleaf-web",
                    "package": name,
                    "version": version,
                    "severity": "unknown",
                    "title": str(vuln.get("description", ""))[:300],
                    "url": f"https://osv.dev/vulnerability/{identifier}" if identifier else "",
                    "fixed_in": ", ".join(vuln.get("fix_versions") or []),
                }
            )
    return rows, versions


def npm_rows(project, data):
    """npm audit's `--json` (v7 and later): {"vulnerabilities": {name: {"severity", "range", "via", "fixAvailable"}}}:
    one row per advisory a package's `via` names (a package listed only through another names none)."""
    rows = []
    for name, entry in ((data or {}).get("vulnerabilities") or {}).items():
        for via in entry.get("via") or []:
            if not isinstance(via, dict):
                continue
            severity = str(via.get("severity") or entry.get("severity") or "")
            fix = entry.get("fixAvailable")
            rows.append(
                {
                    "id": str(via.get("source") or via.get("url") or ""),
                    "ecosystem": "npm",
                    "project": project,
                    "package": name,
                    "version": str(via.get("range") or entry.get("range") or ""),
                    "severity": severity if severity in SEVERITIES else "unknown",
                    "title": str(via.get("title", ""))[:300],
                    "url": str(via.get("url", "")),
                    "fixed_in": f"{fix.get('name')} {fix.get('version')}" if isinstance(fix, dict) else "",
                }
            )
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pip", help="pip-audit --format json's output")
    parser.add_argument("--npm", action="append", default=[], help="project=path of npm audit --json's output")
    parser.add_argument("--version", action="append", default=[], help="name=version to report (next=16.0.1)")
    parser.add_argument("--commit", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--strict", action="store_true", help="exit 1 when an input is not ok (the file is written)")
    args = parser.parse_args(argv)
    advisories, versions, inputs = [], {}, []
    if args.pip:
        data, problem = read(args.pip)
        problem = problem or unusable(data, "dependencies")
        rows, found = pip_rows(data) if not problem else ([], {})
        advisories += rows
        versions.update(found)
        inputs.append({"source": "pip-audit", "path": args.pip, "ok": not problem, "error": problem})
    for given in args.npm:
        project, _, path = given.partition("=")
        data, problem = read(path)
        problem = problem or unusable(data, "vulnerabilities")
        advisories += npm_rows(project, data) if not problem else []
        inputs.append({"source": f"npm audit {project}", "path": path, "ok": not problem, "error": problem})
    for given in args.version:
        name, _, version = given.partition("=")
        versions[name] = version
    unique = {(row["ecosystem"], row["project"], row["package"], row["id"]): row for row in advisories}
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": args.commit,
        "versions": versions,
        "inputs": inputs,
        "advisories": sorted(unique.values(), key=lambda row: (row["ecosystem"], row["package"], row["id"])),
    }
    Path(args.output).write_text(json.dumps(report, indent=1))
    print(f"{len(report['advisories'])} advisories written to {args.output}")
    broken = [row for row in inputs if not row["ok"]]
    if args.strict and broken:
        print(
            "Not every audit ran: " + "; ".join(f"{row['source']}: {row['error']}" for row in broken), file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
