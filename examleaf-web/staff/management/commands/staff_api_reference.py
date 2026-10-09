"""manage.py staff_api_reference: every staff endpoint's method, path, permission, query, body and answers, and every
field of what they take and give, as Markdown, from the OpenAPI schema and the views' own permission maps. API.md
"Staff API reference" is its output; staff/tests/test_matrix.py fails when the two differ (run this, paste it)."""

import re

from django.core.management.base import BaseCommand
from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIRequestFactory

from staff.permissions import ANY_STAFF

PREFIX = "/api/v1/staff/"
METHODS = ["get", "post", "put", "patch", "delete"]
SAMPLES = {"role": "SUPPORT", "key": "SHOP_OPEN"}  # path parameters that are not ids


def permission(path, method):
    match = resolve(re.sub(r"\{(\w+)\}", lambda m: SAMPLES.get(m.group(1), "1"), path))
    view = match.func.cls()
    view.kwargs, view.action = match.kwargs, (getattr(match.func, "actions", None) or {}).get(method)
    perm = (
        view.required_permission(getattr(APIRequestFactory(), method)(path)) if hasattr(view, "permissions") else None
    )
    if perm is None:
        return "none: the invitation's token"
    if perm == ANY_STAFF:
        return "any member of staff"
    named = view.permissions.get(view.action, view.permissions.get(method.upper()))
    return f"`{perm}`" + (" (by the key or the body: see the table above)" if callable(named) else "")


def ref(schema):
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[1]
    if schema.get("type") == "array":
        return f"[{ref(schema.get('items', {}))}]"
    if "allOf" in schema:
        return " ".join(ref(part) for part in schema["allOf"])
    if schema.get("type") == "integer":
        return "integer"  # (int32 or int64 by the database's own ranges: not the API's business)
    return schema.get("format") or schema.get("type") or "any"


def body(operation):
    content = (operation.get("requestBody") or {}).get("content", {})
    for kind, item in content.items():
        if kind in ("application/json", "multipart/form-data") and "schema" in item:
            return f"`{ref(item['schema'])}`"
    return ""


def answers(operation):
    parts = []
    for code, response in sorted(operation["responses"].items()):
        content = response.get("content") or {}
        shapes = sorted({ref(item["schema"]) if kind == "application/json" else kind for kind, item in content.items()})
        parts.append(f"{code} " + ", ".join(f"`{shape}`" for shape in shapes) if shapes else str(code))
    return "; ".join(parts)


def field(name, schema, required):
    kind = ref(schema)
    if "enum" in schema:
        kind = " / ".join(str(value) for value in schema["enum"] if value not in ("", None))
    flags = [
        flag
        for flag, on in [
            ("required", name in required),
            ("null", schema.get("nullable")),
            ("read-only", schema.get("readOnly")),
        ]
        if on
    ]
    return f"`{name}` {kind}" + (f" ({', '.join(flags)})" if flags else "")


def referenced(schema, found):
    for value in schema.values() if isinstance(schema, dict) else schema if isinstance(schema, list) else []:
        if isinstance(value, dict | list):
            referenced(value, found)
    if isinstance(schema, dict) and "$ref" in schema:
        found.add(schema["$ref"].rsplit("/", 1)[1])


class Command(BaseCommand):
    help = "Print the staff API reference (API.md) from the OpenAPI schema."

    def handle(self, *args, **options):
        self.stdout.write(reference(), ending="")


def reference():
    schema = SchemaGenerator(api_version="v1").get_schema(request=None, public=True)
    components, rows, used = schema["components"]["schemas"], [], set()
    for path, operations in sorted(schema["paths"].items()):
        if not path.startswith(PREFIX):
            continue
        for method in [name for name in METHODS if name in operations]:
            operation = operations[method]
            referenced(operation, used)
            query = ", ".join(f"`{p['name']}`" for p in operation.get("parameters", []) if p["in"] == "query")
            short = path.removeprefix(PREFIX)
            rows.append(f"| {method.upper()} | `{short}` | {permission(path, method)} | {query} | {body(operation)} | "
                        f"{answers(operation)} |")  # fmt: skip
    pending, seen = sorted(used), set()
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            more = set()
            referenced(components[name], more)
            pending.extend(sorted(more - seen))
    lines = ["| Method | Path | Permission | Query | Body | Answers |", "|---|---|---|---|---|---|", *rows, ""]
    for name in sorted(seen):
        component = components[name]
        if "enum" in component:
            values = ", ".join(f"`{value}`" for value in component["enum"] if value not in ("", None))
            lines.append(f"- **{name}**: one of {values}" if values else f"- **{name}**: null")
            continue
        required = set(component.get("required", []))
        fields = [field(key, value, required) for key, value in component.get("properties", {}).items()]
        lines.append(f"- **{name}**: " + ("; ".join(fields) if fields else ref(component)))
    return "\n".join(lines) + "\n"
