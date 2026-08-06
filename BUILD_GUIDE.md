# Fixture Generator + Verifier — Build Guide (Pritam's part)

All code in this package has been written AND tested (fixture generation,
classification logic, and demo functions all run and pass locally). Only
the actual Docker build/run was not testable in the environment this was
built in — no Docker daemon available there. Verify that piece first,
before anything else, once on a machine with Docker.

## Where to start, why, what

**Start with Docker, not the fixtures.** Everything else in this
component is pure Python logic, already tested. The one genuinely unknown
risk is whether `python:2.7-slim` pulls and runs cleanly in the actual
build environment (confirmed publicly available, but "available" and
"works smoothly on your machine right now" are different things).
De-risk that first, hour one, before building anything on top of it.

**Why this order:** the deck's own five-checkpoint gate rewards a green
pipeline over a clever one. A working Docker plumbing check on a trivial
stub, committed and green in CI by mid-morning, is worth more than a
half-finished sophisticated verifier at the deadline.

**What "done" looks like for this component:** `python orchestrator/verify.py`
runs end to end against the real legacy repo slice, produces
`reports/verification_report.md`, and the GitHub Actions workflow shows
green on the latest commit.

## Step-by-step

### 1. Prove Docker works (15–20 min)
```bash
docker pull python:2.7-slim
docker pull python:3.12-slim
docker run --rm python:2.7-slim python --version
docker run --rm python:3.12-slim python --version
```
If both print a version cleanly, move on. If not, this is today's first
blocker to solve — everything downstream depends on it.

### 2. Build the two sandbox images from this package (10 min)
```bash
cd fixture_verifier
docker build -f harness/Dockerfile.py2 -t verify-py2 .
docker build -f harness/Dockerfile.py3 -t verify-py3 .
```

### 3. Run the demo end to end (10 min)
The package ships with three working demo functions (`calculate_total`,
`normalize_name`, `apply_discount`) already wired through
`manifest/functions.json`, with `apply_discount` containing a
**deliberate bug** (`//` instead of `/`) so there's a known mismatch to
confirm detection actually works, not just the happy path.

```bash
pip install -r requirements.txt
python orchestrator/fixture_gen.py     # generates fixtures/*.json (already included, but safe to regenerate)
python orchestrator/verify.py          # builds images, runs both sandboxes, classifies, writes report
cat reports/verification_report.md
```

Expected: `calculate_total` and `normalize_name` → PASS. `apply_discount`
→ FAIL, with the bad cases listed showing py2 vs py3 values differing.
**If this is what happens, the whole mechanism is proven correct** —
everything from here is pointing it at the real repo instead of the demo.

### 4. Point it at the real legacy repo slice (remainder of Day 1)
- Replace `legacy/` and `converted/` with symlinks or copies of the real
  bounded slice the team picked
- Update `manifest/functions.json` with the real function names, module
  paths, and argument types (this should come from whoever owns the
  Parser/Analyzer agent — coordinate on the manifest format early, it's
  the interface between your two pieces)
- Add realistic `"range"` hints per argument where the domain isn't
  "any int/float" (see how `discount_percent` is scoped to `[0, 100]` in
  the demo manifest — without this, generated fixtures drift into
  unrealistic values fast)
- Re-run `fixture_gen.py`, commit the frozen fixtures, re-run `verify.py`

### 5. Wire into the team's actual CI (30 min)
The workflow file here lives at `fixture_verifier/.github/workflows/verify.yml`
for packaging purposes — **it needs to move to the repo root's
`.github/workflows/`** once merged with teammates' code, and the
`working-directory: fixture_verifier` line adjusted to wherever this
folder actually lands in the final repo tree.

### 6. Document for the non-negotiables
This component is a strong candidate for the **custom agent** requirement
in `AGENTS_AND_SKILLS.md` — the Verifier has the most distinctive logic
(three-way classification with a "never silently pass" rule). Suggested
entry:

> **Verifier Agent** — compares legacy (Py2) and converted (Py3) function
> output against identical frozen fixtures, classifies every case as
> match/mismatch/ambiguous, and fails the build on anything that isn't a
> confirmed match. Lives in `orchestrator/classifier.py` +
> `orchestrator/verify.py`.
>
> **Custom skill: fixture generation** — type-informed input generation
> using hypothesis strategies plus explicit boundary values, frozen to
> versioned JSON so every verification run compares against identical
> inputs. Lives in `orchestrator/fixture_gen.py`.

## What each file does

| File | Role |
|---|---|
| `manifest/functions.json` | Input contract: which functions, what types, what modules |
| `orchestrator/fixture_gen.py` | Host-side. Generates + freezes test inputs. Run once, not in CI. |
| `orchestrator/docker_manager.py` | Builds images, runs each sandbox via subprocess, handles timeouts |
| `harness/harness.py` | Runs INSIDE both containers. Calls the target function per fixture case. |
| `harness/Dockerfile.py2` / `.py3` | Sandbox definitions |
| `orchestrator/classifier.py` | Normalizes + diffs outputs, classifies match/mismatch/ambiguous |
| `orchestrator/verify.py` | Main entrypoint — ties it all together, writes the report |
| `tests/` | Unit tests for classifier and fixture generator (no Docker needed) |

## Known limitations (be upfront about these, don't get caught by them live)

- **Fixtures test equivalence, not correctness.** If the legacy function
  had a bug, the converted version faithfully reproducing that bug will
  show as a "match." This tool proves "behaves the same," not "was
  correct to begin with."
- **Side-effecting functions won't work well.** Anything touching a
  database, filesystem, or network won't fixture/diff cleanly with this
  design — scope the demo slice to pure(ish) functions.
- **`ambiguous` cases need a human.** By design, nothing auto-resolves to
  "safe" — that's a feature (matches the deck's human-in-the-loop rule),
  but budget review time for it rather than being surprised the pipeline
  isn't 100% green on the first real run.

## Prompts for the agent (if delegating remaining wiring to Cline/Claude)

**Pointing at the real repo:**
> "Update `manifest/functions.json` to describe [list real function
> names/modules/types here]. Do not change the schema — match the
> existing structure exactly, including optional `range` hints for
> numeric arguments where the valid domain is narrower than the raw
> type."

**Extending the type strategy map:**
> "Add a hypothesis strategy to `TYPE_STRATEGIES` in
> `orchestrator/fixture_gen.py` for type `[new type]`, plus a
> corresponding entry in `BOUNDARY_VALUES`. Follow the existing pattern —
> don't restructure the file."

**CI integration:**
> "Move `.github/workflows/verify.yml` to the repo root's
> `.github/workflows/`, merge it as a separate job alongside [teammate]'s
> existing workflow if one exists, and update the `working-directory`
> path to match where `fixture_verifier/` lives in the final repo tree."

Have the agent run in Plan mode for the manifest update (since wrong
types there silently produce garbage fixtures) — Act mode is fine for the
CI path fix, it's low-risk and easy to visually verify.
