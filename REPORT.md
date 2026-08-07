# Agent D report -- CLI, CI/CD, Docs & Demo

For Om, Suryansh, Pritam. Assumes you haven't read the code, only this and
`shared/schemas.py`.

## 1. What was built

- **`cli/convert.py`** -- `legacy-pyconvert` CLI (click). Three
  subcommands: `convert` (full pipeline: classify -> convert/critic ->
  verify -> `build/summary.json`), `verify` (re-apply gate semantics to an
  existing summary.json), `report` (human or GitHub-summary output). It
  imports the real classifier/converter/verifier if importable, falls back
  to local stubs in `cli/_stubs.py` otherwise -- no code changes needed as
  each of your modules lands, only that the import path resolves.
- **`.github/workflows/ci.yml`** -- runs on push/PR, installs the tool,
  pulls both sandbox images, runs the pipeline against the demo slice,
  publishes results to the job summary. Never gates on pass/fail counts
  (see #4).
- **`action.yml`** -- composite GitHub Action (not a Docker container
  action, see ARCHITECTURE.md for why) packaging the tool for any repo to
  install. Real exit-code and PR-comment semantics, not a stub.
- **`shared/schemas.py`** -- DRAFT contract (pydantic models) written to
  unblock the stubs. Not final -- see #3 and please confirm/correct
  against your real modules.
- **`ARCHITECTURE.md`** / **`AGENTS.md`** -- stack choices, full data flow,
  and the must-always/must-never rules, enforced in code not just prose.

## 2. Commands to run

```bash
pip install -e .                                   # editable install, entry point: legacy-pyconvert

legacy-pyconvert convert demo/legacy_slice --out build/    # full pipeline
legacy-pyconvert report --out build/                        # human summary
legacy-pyconvert report --out build/ --format github        # markdown for a PR/summary
```

`convert` takes `--fail-on-mismatch/--no-fail-on-mismatch` (default: fail).
Exit code: 0 unless a clear mismatch/failed conversion exists AND
fail-on-mismatch is on.

## 3. critic_verdict / verifier verdict -> final status

`cli/convert.py`'s `_resolve_status()` is the *only* place a `pass` gets
produced. Full mapping in ARCHITECTURE.md; short version:

- `conversion_failed` -> `fail`, verifier is **never called**.
- classifier tag `unsupported` -> `fail` directly, converter never called
  either (no LLM spend).
- `clear_mismatch` -> `fail`, always, regardless of critic verdict.
- `ambiguous` -> `needs_review`, always.
- `exact_match` + critic `approved` -> the only path to `pass`.
- `exact_match` + critic `needs_review` -> capped at `needs_review` (a
  critic concern is never silently overruled by a clean sandbox run).

**Please confirm:** `CriticVerdict.CONVERSION_FAILED` and
`VerifierVerdict` (`exact_match`/`clear_mismatch`/`ambiguous`) in
`shared/schemas.py` are my best guess at your real contracts, not
confirmed. If your actual enum names/shapes differ, tell me directly --
don't code around the mismatch on your end.

## 4. CI state

Stub steps only right now -- `cli/_stubs.py` implements crude but real
stand-ins (regex-based classification, regex-based mechanical fixes,
ast.parse + leftover-py2-marker check instead of a real sandbox diff).
Internal `ci.yml` always runs with `--no-fail-on-mismatch` so counts never
block our own build while modules are still landing -- `action.yml` (what
external repos get) defaults to blocking, that's the real product
behavior. First commit (`Day 1: stub-first CLI, CI, action.yml, and demo
slice`) is on `main` locally now; push + first Actions run still TODO.

Swap-in points, in order of what unblocks the most: Om's classifier
(`agents.classifier.classify_source`), then Suryansh's
`agents.converter_critic.graph.run` (already the confirmed import path),
then Pritam's `agents.verifier.verify_function`. Whichever import path
you actually use, tell me if it differs from those three -- `convert.py`
tries them by name and falls back to stubs silently on `ImportError`, so a
typo'd path would look like "still stubbed" instead of erroring loudly.

## 5. Demo slice

13 real functions from CPython 2.7's `Lib/urllib.py` (`demo/legacy_slice/`,
manifest with expected tag + rationale per function). Verified against a
real `python:2.7-slim` container: valid syntax, correct runtime behavior.
Picked for range: 9 mechanical (`template_match`) URL-splitting functions,
plus 4 genuinely `llm_needed` ones -- `quote()` is the flagship case (its
`str(bytearray(xrange(256)))` byte-table trick still *runs* after a naive
`xrange->range` fix but silently builds the wrong table -- exactly the bug
class sandboxed diffing catches and "does it run" doesn't), and
`urlencode()` has the old `raise Type, msg, tb` syntax (hard SyntaxError
under Python 3, already confirmed as a `fail` by the stub verifier).

## 6. Known gaps / TODOs

- Push to a GitHub remote + confirm the first Actions run is green
  (blocked on repo remote not being set up yet).
- `shared/schemas.py` needs your sign-off, especially `conversion_failed`.
- `action.yml`'s PR-comment step needs `permissions: pull-requests: write`
  granted by whichever workflow calls it -- not something the action
  itself can set.
- Real sandbox images are pulled in CI but unused until Pritam's verifier
  lands -- stub verifier does a parse+marker check only, not a real diff.
- No unsupported-tagged function in the demo slice yet (see manifest) --
  if useful for testing that path, say so and I'll add one.
