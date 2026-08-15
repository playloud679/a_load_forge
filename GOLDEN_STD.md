# GOLDEN_STD.md - Development Contract

This document defines the working method for this repository.  The goal is
fast, correct development with low token waste.

## 1. Branching

Do not push or publish unless explicitly requested.

Before staging or committing:

```bash
git status -sb
git diff --stat
git diff --check
```

Stage explicit files only.  Do not use broad staging when the worktree contains
unrelated or untracked files.

## 2. Documentation Contract

Documentation must stay in sync with source.

| Changed file | Required documentation |
|---|---|
| `src/acoustics.py` | `docs/acoustics.md` |
| `src/dccav.py` | `docs/dccav.md` |
| `src/engine.py` | `docs/engine.md` |
| user-visible UI behavior | `USER_GUIDE.md` and/or `docs/INDEX.md` |
| release/version behavior | `CHANGELOG.md`, `VERSION`, package metadata |

If a new `src/*.py` module is added, create the matching `docs/<module>.md`.

Docs should explain public APIs, invariants, assumptions, edge cases, failure
modes and the tests protecting the behavior.

## 3. Source-to-UI Contract

If backend behavior changes, update every dependent UI and caller.

Checklist:

- New function/module: add caller or UI integration.
- Changed function signature: update all call sites and tests.
- Changed behavior: update user-facing text if users need to understand it.
- New parameter: expose it only where it is relevant.
- Generated output: update plots, labels, downloads and tests.

## 4. Token-Efficient Reading

Preferred order:

1. Read `AGENTS.md`, `README.md`, `docs/INDEX.md` and `docs/acoustics.md`.
2. Use `rg` to locate relevant symbols.
3. Read only the source slices needed.
4. Read focused tests around the behavior.
5. Expand scope only when evidence requires it.

Preferred commands:

```bash
rg "symbol_or_text"
rg --files
sed -n '120,220p' file.py
git diff -- file.py
```

## 5. Change Scope

Keep edits narrow.

Do:

- fix the requested behavior
- update directly related tests and docs
- preserve existing style
- use existing helpers and patterns

Do not:

- refactor unrelated code
- rename unrelated things
- reformat whole files
- delete user work
- modify generated or temporary files unless explicitly required

If the worktree is dirty, assume unknown changes are user-owned.

## 6. Comments

Use comments sparingly for invariants, edge cases or non-obvious choices.  Put
longer reasoning in the matching doc file.

## 7. Testing

Focused checks:

```bash
.venv/bin/python -m py_compile ui_app.py src/acoustics.py src/engine.py tests/test_all.py
.venv/bin/python tests/test_all.py -m "acoustic-load smoke"
```

UI check:

```bash
.venv/bin/python -c 'from streamlit.testing.v1 import AppTest; at = AppTest.from_file("ui_app.py", default_timeout=30); at.run(); assert not at.exception, at.exception'
```

Full active suite:

```bash
make test
```

Report exact validation commands and outcomes.  Do not claim a test passed
unless it was actually run.

## 8. Versioning

For release-style work, update:

- `VERSION`
- package metadata such as `pyproject.toml`
- `CHANGELOG.md`
- user docs when behavior is visible
