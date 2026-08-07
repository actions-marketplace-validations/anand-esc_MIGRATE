# Architecture

"Deploy or Die" converts legacy Python 2 functions to Python 3 and proves
behavioral equivalence by running both versions in sandboxed containers and
diffing their outputs, rather than trusting that the conversion "looks
right."

## Stack per agent

| Agent | Owns | Stack |
|---|---|---|
| Om | Parser & Classifier | `ast` / `lib2to3` (parsing + known-pattern detection); optional `libcst` if formatting/comment preservation is worth the setup cost |
| Suryansh | Converter + Critic | Anthropic Claude API via the official `anthropic` Python SDK, `pydantic` for structured converter/critic output, LangGraph internally to sequence convert -> critique |
| Pritam | Fixture Generator + Verifier | `hypothesis` (or a custom type-informed generator) for fixtures; Docker Engine (`python:2.7-slim`, `python:3.12-slim`) for sandboxing; `deepdiff` for structured diffing of captured outputs |
| Soumini (Agent D) | CLI, CI/CD, Docs, Demo | `click` for the CLI, GitHub Actions for CI and for packaging the tool as a reusable action |

## Data flow

```
Legacy repo slice (demo/legacy_slice/)
        |
        v
Parser & Classifier (Om)
  tags each function: template_match | llm_needed | unsupported
        |
        +-- template_match --> local template engine (Suryansh's converter, no API call)
        +-- llm_needed      --> Claude convert + critic pass (Suryansh)
        +-- unsupported     --> no conversion attempted (see below)
        |
        v
ConversionResult { converted_source, critic_verdict }
  critic_verdict: approved | needs_review | conversion_failed
        |
        v
Fixture Generator + Verifier (Pritam)
  runs original in python:2.7-slim, converted in python:3.12-slim,
  diffs outputs against generated fixtures
        |
        v
VerificationResult.verdict: exact_match | clear_mismatch | ambiguous
        |
        v
convert.py._resolve_status()  <-- the ONE place a PASS is decided
        |
        v
build/summary.json (counts + per-function detail)
        |
        v
CI/CD gate: internal ci.yml (always green, informational) and
            action.yml (blocks merge on clear mismatch, product default)
```

## Shared schemas

`shared/schemas.py` is the actual source of truth for every type mentioned
below -- read it directly, not this summary, since it will drift as
classifier/converter/verifier land for real. Current status: **DRAFT**,
written by Agent D on Day 1 to unblock `cli/convert.py` against stubs, not
yet confirmed by Om/Suryansh/Pritam against their real modules. In
particular:

- `ClassifiedFunction` (Om's classifier output) -- shape not yet confirmed.
- `CriticVerdict.CONVERSION_FAILED` (Suryansh's addition to the base
  contract, per the brief) -- included as a placeholder value pending his
  confirmation of the actual enum name/shape.
- `VerifierVerdict` (`exact_match` / `clear_mismatch` / `ambiguous`) --
  assumed to be Pritam's three-way verdict; not yet confirmed.

If your real module's output doesn't match `shared/schemas.py`, tell Agent
D rather than coding around the mismatch locally -- `cli/convert.py` is
written to depend on these types by name, so a silent local workaround
would make the CLI wrong without anyone noticing.

## How `conversion_failed` and ambiguous propagate

This is `cli/convert.py`'s core non-negotiable, and it's enforced in code
(`_resolve_status()`, the single function that is allowed to produce a
`PASS`), not just documented here.

**`critic_verdict == conversion_failed`**: the function is recorded as
`FAIL` immediately and Pritam's verifier is **never called** for it --
there is no `converted_source` to sandbox-diff, and calling the verifier
with a failed conversion would either crash it or force it to invent a
meaningless verdict. The batch does **not** halt: one function's
conversion failure shouldn't hide the results of the other N-1 functions,
but it must never be silently dropped from the report either -- it shows
up in `build/summary.json` counted under `fail`, with `detail` set to the
critic's notes.

**`classification tag == unsupported`**: never routed to the converter at
all (so never touches the LLM either -- see AGENTS.md). Recorded as `FAIL`
directly, with the classifier's `reason` as detail.

**Verifier verdict -> final status** (the full mapping, all decided in
`_resolve_status()`):

| critic_verdict | verifier_verdict | final status | why |
|---|---|---|---|
| conversion_failed | (verifier never called) | FAIL | no output to verify |
| approved | exact_match | **PASS** | the only combination that passes |
| approved | ambiguous | needs_review | sandbox diff wasn't conclusive |
| approved | clear_mismatch | FAIL | real behavioral bug |
| needs_review | exact_match | needs_review | critic's concern isn't discarded just because the sandbox run was clean |
| needs_review | ambiguous | needs_review | both signals agree something's unresolved |
| needs_review | clear_mismatch | FAIL | clear mismatch always wins |

Rationale for the `approved` + `exact_match` gate on `needs_review`: the
sandbox diff is the authoritative behavioral signal, but a critic that
flagged a concern has seen something the fixtures might not exercise (e.g.
an edge case fixtures don't happen to hit). Capping at `needs_review`
instead of `PASS` keeps a human in the loop without throwing away the
sandbox result.

## Status semantics (product decision, enforced in two places)

- **Internal CI** (`.github/workflows/ci.yml`): runs with
  `--no-fail-on-mismatch` always, so the pipeline's own counts never gate
  the internal build. This is deliberate -- Day 1-2 of a hackathon is
  exactly when counts fluctuate as classifier/converter/verifier get wired
  in one at a time, and gating our own CI on that would make "green"
  meaningless. Counts are still published to the job summary every run, so
  regressions stay visible without blocking commits.
- **The reusable action** (`action.yml`), i.e. what a consuming repo
  actually gets when they install this tool: `fail-on-mismatch` defaults
  to `true`. All-exact-match succeeds; any clear mismatch fails the job
  (blocks merge if the check is required -- a clear mismatch is a real
  bug); any needs-review item still exits zero but posts a PR comment and
  a warning annotation, so ambiguous cases stay visible without blocking
  every PR that touches legacy code.

## Why action.yml is a composite action, not a Docker container action

GitHub-hosted runners already have a Docker daemon on the host, which is
exactly what Pritam's sandbox containers need directly (`docker run
python:2.7-slim ...` / `docker run python:3.12-slim ...`). A Docker
container action runs the whole action nested inside its own container, so
reaching the host's Docker daemon from in there needs Docker-in-Docker
with privileged access -- something GitHub-hosted runners don't give
container actions by default. A composite action's steps run directly on
the runner, so `docker run` works exactly the way it does in Pritam's
local testing, with no extra privilege needed.

## Known deviation from the original step sketch

An earlier planning pass sketched `action.yml` as five granular steps:
classify-and-convert -> run Py2 sandbox -> run Py3 sandbox -> verify/diff.
The shipped `action.yml` collapses the last three into one step
("Classify, convert, and verify"), because the agreed verifier contract is
a single call -- `verify(original, converted) -> verdict` -- with both
sandbox runs happening *inside* that call. There's no function boundary at
the CLI layer to hang separate steps off without inventing one Pritam
didn't sign up for. If Pritam's real verifier ends up exposing separate
"run py2" / "run py3" / "diff" entry points, `action.yml` can be split
back into granular steps with no change to `cli/convert.py`.
