# Test papers

Copies, byte for byte, of a few files of the books repository `LazyIndianBook/Class-12-Assam` (commit `0e64cdf`,
copied on 8 October 2026). The books repository is the source of truth: never edit these here; copy them again.

The layout is the books repository's, so this folder works as a `--root`: `manage.py import_papers --all --fixtures`
(the same as `--root content/fixtures/papers`), `manage.py import_chapter_insights --fixtures`, then
`manage.py build_quiz_items`. The tests (`content/tests.py`) and the Playwright backend
(`examleaf-frontend/scripts/e2e-backend.sh`) import from here, so CI needs no checkout of the books.

| Files | Why |
|---|---|
| `production/<subject>/papers_md/<CODE>-E01, -M01, -H01` `.md` and `-solutions.md` | one paper of each tier per subject: 12 papers |
| `production/physics/papers_md/PHY-E02` | the Playwright journeys use PHY-E01 (the open sample) and PHY-E02 (behind log-in) |
| `production/<subject>/format.json` | marks, time and parts of the papers; the Board's marks per chapter |
| `production/<subject>/orders/ch*.md` | the chapter and textbook-section tags of the questions (all chapters) |
| `production/<subject>/pyq/ch01.md` | one chapter's previous-year questions, for `import_chapter_insights` |

To refresh, from the platform repository's root with the books checked out beside it:

```sh
src="../Class 12/production"; dst=examleaf-web/content/fixtures/papers/production
for f in $(cd "$dst" && find . -type f); do cp "$src/$f" "$dst/$f"; done
```
