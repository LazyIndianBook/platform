import json
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

rows = []

def walk(patterns, prefix="", ns=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            sub_ns = ns + (p.namespace + ":" if p.namespace else "")
            walk(p.url_patterns, prefix + str(p.pattern), sub_ns)
        elif isinstance(p, URLPattern):
            cb = p.callback
            view = getattr(cb, "view_class", None) or getattr(cb, "cls", None)
            actions = getattr(cb, "actions", None)
            initkw = getattr(cb, "initkwargs", None)
            name = cb.__name__ if hasattr(cb, "__name__") else repr(cb)
            mod = cb.__module__
            if view is not None:
                name = view.__name__
                mod = view.__module__
            rows.append(
                {
                    "route": prefix + str(p.pattern),
                    "name": (ns + p.name) if p.name else "",
                    "view": f"{mod}.{name}",
                    "actions": actions,
                    "kwargs": {k: repr(v) for k, v in (p.default_args or {}).items()},
                }
            )

walk(get_resolver().url_patterns)
print(json.dumps(rows, indent=1, default=str))
