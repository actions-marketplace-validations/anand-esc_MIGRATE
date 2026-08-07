# AGENTS.md -- rules, not architecture

This file states what the pipeline must always and must never do. For what
the code actually does and why it's built that way, see `ARCHITECTURE.md`.
These rules are enforced in `cli/convert.py`'s control flow (see
`_resolve_status()` and `_run_one_function()`), not just written down here
-- if you find code that violates one of these, it's a bug.

## Must always

- **Always run in a sandbox before reporting success.** A function is
  never marked `pass` on the strength of the converter/critic alone. Only
  Pritam's verifier, running the original and converted code in isolated
  containers against generated fixtures, can produce a `pass`.
- **Always treat the sandbox diff as the authoritative behavioral signal.**
  If the verifier says `clear_mismatch`, the function is `fail`, full
  stop, regardless of what the critic said.
- **Always surface every function in the report.** `build/summary.json`
  accounts for every classified function -- pass, fail, or needs-review.
  Nothing is dropped from the output because it was inconvenient.
- **Always preserve a critic's concern.** If Suryansh's critic flags a
  function as `needs_review`, that concern survives into the final status
  even if the sandbox diff comes back clean (capped at `needs_review`, not
  `pass`). A clean sandbox run doesn't get to overrule a human-relevant
  concern the critic already raised.
- **Always keep needs-review visible without blocking merges.** In the
  reusable action, an ambiguous or critic-flagged function exits zero but
  still produces a PR comment and a warning annotation. Visibility and
  blocking are two different levers -- don't conflate them.

## Must never

- **Never silently mark an ambiguous or failed result as passing.** This
  is the project's core non-negotiable. There is exactly one function in
  the codebase (`_resolve_status()` in `cli/convert.py`) allowed to
  produce a `pass` verdict, and it only does so for
  `critic_verdict == approved` AND `verifier_verdict == exact_match`
  together.
- **Never send a `conversion_failed` function to the verifier.** If
  Suryansh's converter/critic couldn't produce usable Python 3 for a
  function, there is nothing to sandbox-diff. That function is recorded as
  `fail` and the verifier is never called for it.
- **Never call the LLM for a function that isn't classified `llm_needed`.**
  Template-matched functions are converted by the local template engine
  only. Every LLM call costs real time and money in a hackathon budget and
  every LLM call is a place a hallucination can creep in -- don't spend
  either on a function a mechanical rule can already handle correctly.
- **Never call the converter/critic at all for a function classified
  `unsupported`.** No template, no LLM call, no verifier call. It's
  recorded as `fail` directly with the classifier's reason as the detail.
- **Never let a single function's `conversion_failed` halt the batch.**
  Report it, count it as `fail`, and keep going -- one function's failure
  should never hide the results of everything else in the run.
- **Never let internal CI's own pass/fail counts gate the internal build.**
  `.github/workflows/ci.yml` runs with `--no-fail-on-mismatch` on purpose,
  because counts are expected to fluctuate as modules land through Day 1-2
  -- but this rule applies only to our own internal CI. It does **not**
  apply to `action.yml`, where `fail-on-mismatch` defaults to `true` for
  every repo that installs this tool as a product.
- **Never redefine `shared/schemas.py` unilaterally to route around a
  teammate's actual output shape.** If a real module's output doesn't
  match the schema, that's a conversation with its owner, not a silent
  local workaround in `cli/convert.py`.
