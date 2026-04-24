# Architecture-lint Override Log

Records every `--no-verify` commit that bypassed `scripts/architecture_lint.py` or
`scripts/wiki_cite_lint.py`. Each entry must have a commit hash, reason, and an
approval pointer (plan section or wiki page).

Any `git commit --no-verify` that is NOT listed here is unauthorized drift.
To cross-check: `git log --grep='#override:'` should return exactly the commits
listed below.

---

## 2026-04-24 — Bootstrap commit: create docs/architecture.yml + docs/ARCHITECTURE.md + docs/override-log.md

- **Commit:** 9f6db24 — `docs(phase-01): bootstrap architecture.yml + ARCHITECTURE.md + override-log.md  #override: bootstrap`
- **Override tag:** `#override: bootstrap`
- **Reason:** `scripts/architecture_lint.py` cannot lint a file that is being created in
  the same commit as the lint target (circular dependency: the file being validated does
  not exist yet when the hook runs, and the hook script itself is installed in the next
  commit). The next commit (Task 2: installing architecture_lint + wiki_cite_lint into
  pre-commit) is non-bootstrap and enforces normally.
- **Approved by:** Planner note in
  `.planning/phases/01-foundation-infrastructure-spine-data-pipeline-economics-gate/01-04-PLAN.md`
  Task 1 `<action>` block. The planning context explicitly designates this as the one-time
  bootstrap exception to the `--no-verify` prohibition.
- **Scope:** Creation of `docs/ARCHITECTURE.md`, `docs/architecture.yml`,
  `docs/override-log.md` only. Does not cover any subsequent source changes.

---

*Future entries go here. Append a new `##` section for each bypass, following the format above.*
