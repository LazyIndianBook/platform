"""What the System page reads that is written elsewhere: a backup's SHA-256 beside it (manage.py upload_backup), and
CI's dependency report made from pip-audit's and npm audit's JSON (scripts/dependency_report.py)."""

import hashlib
import importlib.util
import json

from django.conf import settings as django_settings
from django.core.files.storage import storages
from django.core.management import call_command

SCRIPT = django_settings.BASE_DIR / "scripts" / "dependency_report.py"


def test_a_backup_is_uploaded_with_its_sha256_beside_it(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "backups": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path / "b"}},
    }
    dump = tmp_path / "examleaf-20261009-020000.dump"
    dump.write_bytes(b"PGDMP" + b"1" * 5000)
    call_command("upload_backup", str(dump))
    bucket = storages["backups"]
    checksum = bucket.open("database/examleaf-20261009-020000.dump.sha256").read().decode().split()
    assert checksum == [hashlib.sha256(dump.read_bytes()).hexdigest(), "examleaf-20261009-020000.dump"]


def test_the_ci_report_joins_pip_audits_and_npm_audits_findings(tmp_path):
    spec = importlib.util.spec_from_file_location("dependency_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pip = {"dependencies": [
        {"name": "django", "version": "6.1.2", "vulns": []},
        {"name": "pillow", "version": "11.0.0", "vulns": [{"id": "PYSEC-2026-1", "fix_versions": ["11.0.1"],
                                                           "description": "A crafted image"}]},
    ]}  # fmt: skip
    npm = {"vulnerabilities": {
        "next": {"severity": "critical", "range": "<16.0.2", "fixAvailable": {"name": "next", "version": "16.0.2"},
                 "via": [{"source": 1100, "title": "Middleware bypass", "url": "https://github.com/advisories/GHSA-x",
                          "severity": "critical", "range": "<16.0.2"}]},
        "postcss": {"severity": "moderate", "via": ["next"], "fixAvailable": True},  # through another: no row
    }}  # fmt: skip
    (tmp_path / "pip.json").write_text(json.dumps(pip))
    (tmp_path / "npm.json").write_text(json.dumps(npm))
    out = tmp_path / "report.json"
    args = ["--pip", str(tmp_path / "pip.json"), "--npm", f"admin={tmp_path / 'npm.json'}"]
    args += ["--npm", f"frontend={tmp_path / 'missing.json'}", "--commit", "abc", "--output", str(out)]
    assert module.main(args) == 0
    report = json.loads(out.read_text())
    assert report["commit"] == "abc" and report["versions"] == {"django": "6.1.2"}
    rows = {(row["ecosystem"], row["package"]): row for row in report["advisories"]}
    assert set(rows) == {("npm", "next"), ("pypi", "pillow")}
    assert rows[("npm", "next")]["severity"] == "critical" and rows[("npm", "next")]["fixed_in"] == "next 16.0.2"
    assert rows[("pypi", "pillow")]["severity"] == "unknown" and rows[("pypi", "pillow")]["fixed_in"] == "11.0.1"
    missing = next(row for row in report["inputs"] if row["source"] == "npm audit frontend")
    assert missing["ok"] is False and missing["error"].startswith("FileNotFoundError")


def test_an_audit_that_did_not_run_is_unreadable_not_clean_and_strict_fails_on_it(tmp_path):
    spec = importlib.util.spec_from_file_location("dependency_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry_down = {"message": "request to the registry failed", "error": {"summary": "", "detail": ""}}
    (tmp_path / "admin.json").write_text(json.dumps(registry_down))  # npm audit when it could not ask the registry
    (tmp_path / "frontend.json").write_text(json.dumps({"auditReportVersion": 2, "vulnerabilities": {}}))  # clean
    (tmp_path / "pip.json").write_text("")  # pip-audit killed before it wrote
    out = tmp_path / "report.json"
    args = ["--pip", str(tmp_path / "pip.json"), "--npm", f"admin={tmp_path / 'admin.json'}"]
    args += ["--npm", f"frontend={tmp_path / 'frontend.json'}", "--output", str(out)]
    assert module.main(args) == 0  # the report says what it saw ...
    seen = {row["source"]: row for row in json.loads(out.read_text())["inputs"]}
    assert seen["npm audit admin"]["ok"] is False and "registry" in seen["npm audit admin"]["error"]
    assert seen["pip-audit"]["ok"] is False and seen["npm audit frontend"]["ok"] is True
    assert module.main([*args, "--strict"]) == 1  # ... and CI, which asks for --strict, makes no artifact of it
    (tmp_path / "admin.json").write_text(json.dumps({"vulnerabilities": {}}))
    (tmp_path / "pip.json").write_text(json.dumps({"dependencies": [], "fixes": []}))
    assert module.main([*args, "--strict"]) == 0
