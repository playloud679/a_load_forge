# Development and test selection

Load Forge is pre-production. Prefer one targeted check after a coherent edit;
reserve full local coverage for broad changes, not every commit or CSS tweak.
`AGENTS.md` is the active project contract. Routine edits do not need a version
bump, changelog entry or deployment-document update. Update module documentation
when its described behavior or contract actually changes.

| Change / purpose | Command |
|---|---|
| General local check | `make test` or `make test-fast` |
| One regression | `make test-match MATCH='candidate pool'` |
| Physics across all load families | `make test-smoke` |
| All UI behavior | `make test-ui` |
| Broad changes / full simulator | `make test-all` |
| Runner selection and output handling | `make test-runner` |
| Repository paths/docs/reload | `make test-contracts` |
| Strict catalog data audit | `make test-catalog` |
| Legacy sibling-project integration | `make test-crawler` |

For layout changes, inspect the affected view. AppTest checks widget behavior
and execution, not browser CSS rendering. Avoid running every command in the
table for one change. CI runs the full simulator suite once, without a redundant
startup AppTest.

## Runner

`tests/test_all.py` retains the existing checks, with explicit `group="ui"`
and `group="crawler"` registrations; the default group is `core`. Selection
never depends on a test's display name. Register new AppTests as `ui`, including
tests that mix export/unit assertions with an application run.

- No flags: all local simulator tests (`core` + `ui`).
- `--fast`: `core` only; no AppTests or sibling crawler checks.
- `--ui`: UI group only, including tests whose labels do not begin with “UI”.
- `--smoke`: acoustic-load smoke checks.
- `--crawler`: legacy crawler checks only; explicitly extends imports into
  `../load_forge_crawler`. Ordinary runs do not add that workspace to import paths.
- `--match TEXT` / `-m TEXT`: narrow the selected group by label; repeat to match
  any of several texts. No matches returns exit code 2.
- `--list`: list selected labels and explicit groups without executing tests.
- `--time`: display successful test timings along with the summary.
- `--verbose`: stream raw output for debugging.

Group flags are mutually exclusive. The existing crawler tests are retained
for migration/reference, but excluded from normal simulator validation; they
are not silently removed or counted as passing.

## Output

Normal runs use `tests/suite_output.py` to execute the suite in one child process
and capture stdout/stderr in a unique `.local/test-logs/suite-*.log` file. The
terminal shows the log path, pass/fail/skip counts, elapsed time and exit status.
Failures additionally show up to ten failed labels and a 30-line failure excerpt
(the last 40 log lines if the process fails outside a test). All tracebacks and
warnings remain in the file. The child exit status is preserved.
The directory is already gitignored; old logs may be deleted when no longer needed.
CI uploads these logs when validation fails.

Read only relevant failures from the log rather than pasting megabytes into
agent context. `--list` and `--help` bypass capture for interactive use.
