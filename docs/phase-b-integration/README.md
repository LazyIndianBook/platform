# Phase B integration: the briefs and the tools

How Phase B of the Admin Control Panel was built (10 October 2026): eleven module packages written in parallel by
agents in git worktrees from one set of briefs, merged one by one onto the integration branch `phase-b`, then a wave
of verification packages (the ERPNext shadow run, the documentation, the security review, the deployment
carry-through). Kept here so that Phases C to E can follow the same pattern.

- `briefs/COMMON.md`: the rules every package followed (one module file per package mounted from `staff/urls.py`,
  models at the end of `models.py` under a `# Phase B: <module>` marker, a catalogue row, a role row and a matrix row
  for every endpoint, API.md regenerated, the console's module pattern, the report format). `briefs/P<n>-*.md`: one
  brief per package, with the integration's notes appended where the tech lead took a decision while merging.
- `tools/integrate.sh`: `merge <branch>` (no-ff; stops on conflicts), `regen` (merge migrations, the API reference
  in API.md, `openapi.json` and the console's types), `check` (ruff, migrations, the backend suite, the console's
  checks), `pg` (the backend suite on the local PostgreSQL). Paths at the top are the tech lead's machine's.
- `tools/union.py`: resolve conflict hunks by keeping both sides (ours first) where both sides only added.
- `tools/hunks.py`: print a conflicted file's hunks (`--edges N` for the first and last lines of each side).
- `tools/resolve.py`: `resolve_hunk(file, n, text_or_callable)` for the hunks a union cannot resolve.
- `tools/tails.py`: rebuild an append-only file (the console client, `shop/models.py`) from the merged prefix, HEAD's
  tail and the branch's section, when a conflict split a function or a class.
- `tools/copy_closers.py`: put back the `},` closers a union loses in the console's `copy.ts`.
- `tools/api_nav.py`: rewrite API.md's Contents block from the headings in file order.

The lessons the merges taught are in the briefs' `AFTER-BATCH-A.md` and in the consolidated CHANGELOG entry; the
merge order and the verification at each merge are in `git log phase-b` (one `Merge <module> (P<n>) into phase-b`
commit per package, each naming its counts).
