# GOLDEN_STD.md - Universal Development & AI Agent Contract

**Specification Version:** `1.1.0`  
**Last Updated:** `2026-08-30`  
**Standard Identifier:** `STD-AGY-DEV-CONTRACT-V1.1`  
**Central Canonical Repository:** `https://github.com/playloud679/dev_standards`

---

> [!IMPORTANT]
> ### Sync & Version Check Rule for AI Coding Assistants
> At the start of a new major task or repository setup, the agent should check whether a newer version of `GOLDEN_STD.md` exists in the canonical repository:
> ```bash
> curl -s https://raw.githubusercontent.com/playloud679/dev_standards/refs/heads/main/VERSION
> ```
> If a newer version is available and compatible with the project, propose synchronizing via:
> ```bash
> curl -s https://raw.githubusercontent.com/playloud679/dev_standards/refs/heads/main/GOLDEN_STD.md -o GOLDEN_STD.md
> ```

---

> [!WARNING]
> ### Universal Context & Conflict-Resolution Disclaimer
> `GOLDEN_STD.md` defines universal engineering standards, safety invariants, and quality rules across software, embedded systems, and audio/acoustic engineering.
>
> **AI Agent Operating Directive**:
> 1. You must ALWAYS verify whether any general rule in this document conflicts with the specific intent, domain constraints, or explicit instructions of the active user request.
> 2. **Precedence Hierarchy**:
>    - **Priority 1**: Explicit user instructions in the active conversation.
>    - **Priority 2**: Project-specific requirements, domain physics, or explicit local architecture.
>    - **Priority 3**: `GOLDEN_STD.md` universal engineering rules.
> 3. If a general guideline contradicts a specific user goal (e.g. rapid prototype vs strict production gating, experimental algorithm vs classic invariant), **the user request and project intent take precedence**.
> 4. In case of ambiguity, decide reasonably in the user's best interest or briefly ask for clarification rather than stubbornly applying a conflicting general rule.

---

### Specification Revision History

| Version | Date | Author / Context | Changes / Additions |
|---|---|---|---|
| `1.1.0` | 2026-08-30 | Core Engineering | Added central sync instructions, conflict resolution disclaimer, UI key isolation (§3), Streamlit headless `AppTest` validation (§7), release tagging workflow (§8), Conventional Commits convention (§10), and Audio DSP & Acoustic Test Benches Addendum (§14). |
| `1.0.0` | 2026-08-30 | Core Engineering | Initial baseline specification: branching strategy, documentation contract, token-efficient reading, change scope, tiered testing, error handling, and embedded firmware addendum. |

---

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

Stage explicit files only. Do not use broad staging (`git add .` or `git add -A`) when the worktree contains unrelated or untracked files.

---

## 2. Documentation Contract

Documentation must stay in sync with source.

When modifying a source module, update the matching documentation in the same change:

| Changed file | Required documentation |
|---|---|
| `src/foo.py` | `docs/foo.md` |
| `src/bar.ts` / `*.cpp` | `docs/bar.md` |
| user-visible UI behavior | `USER_GUIDE.md` and/or `docs/INDEX.md` |
| release/version behavior | `CHANGELOG.md`, `VERSION`, package metadata |

If a matching doc does not exist, create it.

Docs should explain public APIs, invariants, assumptions, edge cases, failure modes, and the tests protecting the behavior. Future agents should be able to read docs before source to save tokens.

---

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

UI state and widget key isolation:
- Serialized parameter state keys must have domain prefixes (e.g. `driver_`, `box_`, `ts_`).
- Interactive action buttons, triggers, and temporary widget keys must use distinct prefixes (e.g. `btn_`, `action_`, `temp_`).
- Action buttons must NEVER share prefixes with persistent/serializable parameters to prevent widget state assignment collisions (e.g., `StreamlitValueAssignmentNotAllowedError`).

Primary/base controls must not be hidden in an `Advanced` section. Use `Advanced` only for rare, dangerous, or expert-only controls.

---

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

---

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

Never run destructive commands such as `git reset --hard`, `git checkout -- .`, or broad `rm -rf` unless explicitly requested and confirmed.

---

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

If the explanation needs more than a few lines, put the full reasoning in the matching doc file and leave only a short pointer in code.

---

## 7. Testing

Use tiered tests.

During focused development and minor patches, run the smallest relevant checks:

```bash
python -m py_compile path/to/file.py
python tests/test_specific.py --match "relevant behavior"
# For Streamlit apps, run a headless AppTest to verify rendering with no exceptions:
python -c 'from streamlit.testing.v1 import AppTest; at = AppTest.from_file("app.py", default_timeout=30); at.run(); assert not at.exception, at.exception'
```

For shared logic, run the affected suite after focused checks.

Do not run the full suite after every small edit by default. Full runs are expensive and should be reserved for push, PR, release, or final handoff readiness, or for changes with broad blast radius.

Run the full suite before push, PR, release, or final handoff of a completed change:

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

Report exact validation commands and outcomes. Do not claim a test passed unless it was actually run.

---

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

Release workflow:
1. Bump `VERSION`, package metadata (`pyproject.toml`, etc.), and `CHANGELOG.md`.
2. Update matching docs and verify the full test suite passes (`make test` or `python tests/test_all.py`).
3. Commit with prefix `release: vX.Y.Z - summary`.
4. Create an annotated tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z: summary"`.
5. Push branch and tag: `git push origin dev --tags` (or main when merging).

### Specification (`GOLDEN_STD.md`) Versioning:
When modifying `GOLDEN_STD.md` rules, update its header `Specification Version` (SemVer) and append a row to the `Specification Revision History` table at the top of the file before distributing or committing.

---

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

---

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

Commit with a terse concrete message using Conventional Commits:

```bash
git commit -m "feat(ui): add dual Le metrics display"
```

Conventional commit prefixes:
- `feat:` new user-facing functionality
- `fix:` bug fix
- `docs:` documentation updates
- `test:` test suite updates
- `refactor:` code restructuring without external behavior change
- `release:` version release and metadata synchronization

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

---

## 11. Agent Operating Rules

The agent should:

- explain briefly what it is doing while working
- implement when the request is clear
- ask only when blocked or ambiguity is risky
- prefer existing project patterns over new abstractions
- use structured APIs instead of fragile string manipulation when reasonable
- use `apply_patch` or `replace_file_content` for manual edits
- never overwrite unrelated changes
- never stop at analysis when asked to complete work

---

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

---

## 13. Embedded Firmware Addendum

Use this section for firmware, board-support packages, device drivers, and hardware-facing applications (ESP32, STM32, Arduino, Raspberry Pi, Zephyr, FreeRTOS).

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

When touching any of these, update docs, tests, and the final report with the hardware risk.

Default outputs must boot into a safe state. Actuators should remain disabled until configuration and sanity checks complete.

### Build Matrix

Document all build environments and board variants.

Examples:

```bash
pio run -e esp32-c6-devkitc-1
pio run -e release
cmake --build build
make firmware
```

For minor patches, build only the affected target. For shared drivers, HAL/platform code, protocol changes, or release readiness, build every affected environment.

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

If hardware-facing behavior changed, add a smoke test on the real board before release when hardware is available. Keep the smoke test short and explicit:

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

Code comments should mark local invariants briefly. Detailed timing rationale belongs in `docs/timing.md` or the matching module doc.

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

---

## 14. Audio DSP & Acoustic Test Benches Addendum

Use this section for acoustic simulators, impedance analyzers, audio test benches, and loudspeaker DSP.

### Acoustic & Physical Invariants

Never violate physical and electroacoustic constraints:
- **Resonance & Impedance**: $Z_{\text{max}} > R_e > 0$, and bandwidth $f_2 > f_1 > 0$.
- **Quality Factors**: $Q_{ts} = \frac{Q_{ms} \cdot Q_{es}}{Q_{ms} + Q_{es}} < \min(Q_{es}, Q_{ms})$.
- **Half-Power Bandwidth**: If voice coil inductance $L_e$ masks high-frequency crossing $f_2$, resolve via the AES/Thiele-Small geometric mean relation: $f_s = \sqrt{f_1 \cdot f_2} \implies f_2 = \frac{f_s^2}{f_1}$.
- **Inductance Frequencies**: Report voice coil inductance at standard frequencies ($L_e @ 1\text{ kHz}$ and $L_e @ 10\text{ kHz}$) to account for iron losses and eddy current dispersion.
- **Mechanical Resonance Search**: Identify true local maxima (with zero phase crossing) rather than broad `argmax()` across high-frequency inductive ramps up to 20 kHz.

### Audio Device & Sampling Safety

- Validate duplex audio support (stereo input and output channels $\ge 2$) before initiating sweeps.
- Verify sample rate consistency (e.g. 44.1 kHz on both input/output host APIs).
- Add leading/trailing latency cushions (e.g. $\ge 0.5\text{ s}$) to prevent truncating high-frequency chirp tails.
- Handle empty device lists safely without crashing UI rendering.
