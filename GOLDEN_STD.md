# GOLDEN_STD.md - Development Contract

This document defines the working method for this repository and can be copied
into new projects. The goal is fast, correct development with low token waste.

## 1. Branching

Do not develop directly on the default branch.

Use `dev` as the integration branch:

```bash
git switch dev
```

If `dev` does not exist:

```bash
git switch -c dev
git push -u origin dev
```

Default flow:

1. Work on `dev`.
2. Commit scoped changes.
3. Push `dev`.
4. Open a draft PR from `dev` to the default branch when requested.
5. Merge manually after review.

Before staging or committing:

```bash
git status -sb
git diff --stat
git diff --check
```

Stage explicit files only. Do not use broad staging when the worktree contains
unrelated or untracked files.

## 2. Documentation Contract

Documentation must stay in sync with source.

When modifying a source module, update the matching documentation in the same
change:

| Changed file | Required documentation |
|---|---|
| `src/foo.py` | `docs/foo.md` |
| `src/bar.ts` | `docs/bar.md` |
| user-visible UI behavior | `USER_GUIDE.md` and/or `docs/INDEX.md` |
| release/version behavior | `CHANGELOG.md`, `VERSION`, package metadata |

If a matching doc does not exist, create it.

Docs should explain public APIs, invariants, assumptions, edge cases, failure
modes, and the tests protecting the behavior. Future agents should be able to
read docs before source to save tokens.

## 3. Source-to-UI Contract

If backend behavior changes, update every dependent UI and caller.

Checklist:

- New function/module: add caller or UI integration.
- Changed function signature: update all call sites and tests.
- Changed behavior: update user-facing text if users need to understand it.
- New parameter: hide it unless it is relevant for the active mode.
- Disabled component: hide its parameters instead of leaving confusing controls.
- Generated output: update previews, labels, downloads, and tests.

UI rule:

```text
Include selected     -> relevant parameters visible
Include not selected -> related parameters hidden
```

Primary/base controls must not be hidden in an `Advanced` section. Use
`Advanced` only for rare, dangerous, or expert-only controls.

## 4. Token-Efficient Reading

Do not read the whole repo unless needed.

Preferred order:

1. Read `GOLDEN_STD.md`, `AGENTS.md`, `README.md`, and `docs/INDEX.md`.
2. Use `rg` to locate relevant symbols.
3. Read matching docs before source.
4. Read only the source slices needed.
5. Read focused tests around the behavior.
6. Expand scope only when evidence requires it.

Preferred commands:

```bash
rg "symbol_or_text"
rg --files
sed -n '120,220p' file.py
git diff -- file.py
```

Avoid dumping large files into context.

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

Never run destructive commands such as `git reset --hard`, `git checkout -- .`,
or broad `rm -rf` unless explicitly requested and confirmed.

## 6. Code Comments

Comments inside code should be sparse and useful.

Use comments to explain:

- why a non-obvious choice exists
- invariants that future edits must preserve
- geometry, state, API, or UI contracts
- workarounds for library behavior
- edge cases that tests protect

Avoid comments that merely restate the code.

Good:

```python
# Adapter owns driver-side geometry; keep throat flange UI status-only
# while preserving generation defaults for the assembly path.
_ft_sp = _ta_flange_sp
```

Bad:

```python
# Set _ft_sp equal to _ta_flange_sp.
_ft_sp = _ta_flange_sp
```

If the explanation needs more than a few lines, put the full reasoning in the
matching doc file and leave only a short pointer in code.

## 7. Testing

Use tiered tests.

During focused development and minor patches, run the smallest relevant checks:

```bash
python -m py_compile path/to/file.py
python tests/test_specific.py --match "relevant behavior"
```

For shared logic, run the affected suite after focused checks.

Do not run the full suite after every small edit by default. Full runs are
expensive and should be reserved for push, PR, release, or final handoff
readiness, or for changes with broad blast radius.

Run the full suite before push, PR, release, or final handoff of a completed
change:

```bash
make test
```

If the project uses another standard command, use that instead:

```bash
npm test
pnpm test
pytest
cargo test
```

Report exact validation commands and outcomes. Do not claim a test passed unless
it was actually run.

## 8. Versioning

For release-style work, update:

- `VERSION`
- package metadata such as `pyproject.toml`, `package.json`, or `Cargo.toml`
- `CHANGELOG.md`
- user docs when behavior is visible

Version bump rules:

- Patch: bugfix, UX cleanup, docs/test update.
- Minor: new user-facing feature.
- Major: breaking API or behavior change.

Changelog format:

```markdown
## x.y.z (YYYY-MM-DD)

- **Area**: concise description of what changed and why.
- **Docs/Test**: mention updated docs, tests, and version files.
```

## 9. Error Handling

Do not hide failures.

When generation or transformation can fail:

- validate inputs before expensive work
- show a clear user-facing error
- preserve technical detail in logs or tests
- add a regression test for known failures

Generated outputs must satisfy project invariants, for example:

- closed mesh
- positive volume
- single body where expected
- non-empty output
- no silent fallback that changes semantics

## 10. Commit and PR

Before commit:

```bash
git status -sb
git diff --check
```

Before push, PR, release, or final handoff:

```bash
make test
```

Stage only intended files:

```bash
git add file1 file2 docs/file.md tests/test_file.py
```

Commit with a terse concrete message:

```bash
git commit -m "Fix adapter UI state"
```

Push:

```bash
git push origin dev
```

PR body:

```markdown
## Summary

- What changed.
- Why it changed.
- User or developer impact.

## Validation

- Commands run.
- Test results.

## Notes

- Known limitations.
- Anything not run.
```

Default PR state is draft unless the user explicitly asks otherwise.

## 11. Agent Operating Rules

The agent should:

- explain briefly what it is doing while working
- implement when the request is clear
- ask only when blocked or ambiguity is risky
- prefer existing project patterns over new abstractions
- use structured APIs instead of fragile string manipulation when reasonable
- use `apply_patch` for manual edits
- never overwrite unrelated changes
- never stop at analysis when asked to complete work

## 12. Done Definition

A task is done only when:

- requested behavior is implemented
- relevant docs are updated
- relevant focused tests pass
- full suite passes before push, PR, release, or final handoff
- version/changelog are updated when requested
- commit is created when requested
- push/PR is done when requested
- remaining risks are explicitly stated

## 13. Embedded Firmware Addendum

Use this section for firmware, board-support packages, device drivers, and
hardware-facing applications.

Firmware changes must keep software, hardware assumptions, and validation in
sync. A passing build is not enough when a change can affect pins, voltage,
timing, storage, communication, or actuator behavior.

### Required Hardware Docs

Maintain these docs when applicable:

| Area | Suggested doc |
|---|---|
| Board/MCU/clock/flash/RAM assumptions | `docs/hardware.md` |
| Pin assignments, electrical direction, boot states | `docs/pinout.md` |
| Wiring, connectors, power rails, voltage levels | `docs/wiring.md` |
| UART/I2C/SPI/CAN/BLE/WiFi protocol payloads | `docs/protocol.md` |
| Build, flash, debug, monitor commands | `docs/build.md` |
| EEPROM/NVS/flash config layout | `docs/storage.md` |
| Timing, ISR, watchdog, debounce, retry policy | `docs/timing.md` |

If the project uses different names, follow the local convention.

### Hardware Safety Contract

Never silently change:

- pin assignments
- pin direction or default boot state
- voltage/current assumptions
- relay, motor, heater, charger, battery, or high-current behavior
- watchdog, brownout, fail-safe, or emergency-stop behavior
- persistent storage layout
- protocol framing, baudrate, checksum, or compatibility

When touching any of these, update docs, tests, and the final report with the
hardware risk.

Default outputs must boot into a safe state. Actuators should remain disabled
until configuration and sanity checks complete.

### Build Matrix

Document all build environments and board variants.

Examples:

```bash
pio run -e esp32-c6-devkitc-1
pio run -e release
cmake --build build
make firmware
```

For minor patches, build only the affected target. For shared drivers,
HAL/platform code, protocol changes, or release readiness, build every affected
environment.

### Upload Policy

Do not flash hardware by default.

Upload only when:

- explicitly requested by the user
- required to validate a hardware-facing change
- the target board and port are known

Always state the target and port before upload.

Examples:

```bash
pio run -e board_name -t upload --upload-port /dev/cu.usbmodem101
```

Never guess a serial port when multiple devices are connected.

### Embedded Test Hierarchy

During minor firmware patches:

```bash
pio run -e affected_env
python -m pytest tests/test_specific.py
```

For shared firmware logic:

```bash
pio run -e affected_env_1
pio run -e affected_env_2
python -m pytest
```

Before push, PR, release, or final handoff:

```bash
pio run
python -m pytest
```

If hardware-facing behavior changed, add a smoke test on the real board before
release when hardware is available. Keep the smoke test short and explicit:

- boot confirms safe state
- expected peripheral initializes
- serial/log output is sane
- actuator outputs remain safe unless intentionally tested
- protocol command returns expected response

### Realtime and Timing Contract

Document and protect:

- ISR responsibilities and maximum expected duration
- polling rates
- debounce intervals
- timeout values
- retry/backoff behavior
- watchdog feed points
- blocking calls in control loops
- sleep/power-save behavior

Code comments should mark local invariants briefly. Detailed timing rationale
belongs in `docs/timing.md` or the matching module doc.

### Protocol and Storage Contract

Protocol changes require:

- payload/schema docs
- backwards-compatibility note
- parser/encoder tests
- version bump if external behavior changes

Persistent storage changes require:

- layout docs
- migration/default behavior
- corruption or missing-key behavior
- tests for old and new layouts when practical

### Logging Contract

Logs must help debug hardware without breaking realtime behavior.

- Keep high-frequency loops quiet by default.
- Use log levels or compile-time flags.
- Do not print secrets, WiFi credentials, tokens, or private keys.
- Do not add blocking logs in ISR or tight control paths.

### Embedded Done Definition

An embedded task is done only when:

- affected firmware targets build
- relevant unit/host tests pass
- docs match hardware assumptions
- pin/protocol/storage/timing changes are called out
- upload/hardware smoke test is run when required or explicitly skipped with a reason
- full build/test matrix passes before push, PR, release, or final handoff
