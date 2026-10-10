# The repository's shared targets. Each component keeps its own tooling; these run the documentation portal.
PY ?= examleaf-web/.venv/bin/python

.PHONY: docs docs-serve docs-check docs-badges

docs: docs-badges  ## build the documentation portal into site/
	$(PY) scripts/docs/build_site.py
	$(PY) -m mkdocs build --clean

docs-serve: docs-badges  ## read the portal at http://localhost:8008/ while editing
	$(PY) scripts/docs/build_site.py
	$(PY) -m mkdocs serve --dev-addr localhost:8008

docs-check:  ## every Mermaid diagram rendered once (needs npx)
	$(PY) scripts/docs/check_mermaid.py

docs-badges:  ## the local badges from docs/assets/badges/badges.json
	$(PY) scripts/docs/badges.py
