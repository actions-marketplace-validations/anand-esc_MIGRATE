"""
orchestrator/classifier.py

Compares one function's py2-container output against its py3-container
output and classifies every case as:

    match     - outputs are equivalent (after normalization)
    mismatch  - outputs genuinely differ, or only one side errored
    ambiguous - a difference exists that doesn't cleanly resolve either way

Policy: CI fails the build on BOTH mismatch and ambiguous. Nothing ships
unreviewed. Once a human confirms an "ambiguous" case is a benign
difference (float rounding, str/unicode, etc.), add an explicit rule
here - never silently widen the "match" bucket.
"""

from deepdiff import DeepDiff

# Tolerance for float comparisons after DeepDiff's own significant_digits
# handling - kept as a named constant so it's easy to tune, not buried.
SIGNIFICANT_DIGITS = 6


def normalize(value):
    """
    Makes Python 2 and Python 3 output structurally comparable.
    The single most common false-mismatch source is Py2 str/bytes/unicode
    vs Py3's single str type - collapse them before diffing.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {normalize(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def classify_case(py2_case, py3_case):
    """
    py2_case / py3_case: single-case dicts from harness output, e.g.
        {"case_id": 0, "result": ..., "type": "...", "error": None or "..."}
    Returns (classification: str, detail: str or None)
    """
    py2_err, py3_err = py2_case.get("error"), py3_case.get("error")

    if py2_err or py3_err:
        if py2_err and py3_err:
            # Both sides errored. Same error class = treat as match (the
            # behavior - raising - is preserved). Different error class =
            # ambiguous, needs a human to confirm it's the "same" failure.
            py2_kind = py2_err.split(":")[0]
            py3_kind = py3_err.split(":")[0]
            if py2_kind == py3_kind:
                return "match", None
            return "ambiguous", "both errored but with different exception types: {0} vs {1}".format(
                py2_kind, py3_kind
            )
        # One side errored, other didn't - this is the clearest kind of bug.
        return "mismatch", "py2_error={0!r} py3_error={1!r}".format(py2_err, py3_err)

    diff = DeepDiff(
        normalize(py2_case.get("result")),
        normalize(py3_case.get("result")),
        ignore_order=True,
        significant_digits=SIGNIFICANT_DIGITS,
        # A Python 2 int result and a Python 3 float result with the SAME
        # value (e.g. legacy int-division artifacts) are not a real bug -
        # only flag it when the VALUE actually differs.
        ignore_numeric_type_changes=True,
    )
    if not diff:
        return "match", None

    # A diff made up ONLY of plain value changes (no structural changes -
    # no items added/removed, no unresolved type changes) is a confident,
    # genuine behavioral difference: classify as mismatch.
    diff_keys = set(diff.keys())
    if diff_keys <= {"values_changed"}:
        return "mismatch", str(diff)

    # Structural differences (items added/removed, unresolved type
    # changes, etc.) are less clear-cut - flag for human review rather
    # than guess.
    return "ambiguous", str(diff)


def classify_function(func_name, py2_results, py3_results):
    """
    py2_results / py3_results: lists of per-case dicts (harness output),
    same length and same case_id ordering (guaranteed since both ran
    against the identical frozen fixture file).
    Returns a list of per-case classification dicts.
    """
    if len(py2_results) != len(py3_results):
        raise ValueError(
            "Result count mismatch for {0}: py2={1} py3={2}. "
            "Did both containers run against the same fixture file?".format(
                func_name, len(py2_results), len(py3_results)
            )
        )

    out = []
    for py2_case, py3_case in zip(py2_results, py3_results):
        classification, detail = classify_case(py2_case, py3_case)
        out.append(
            {
                "case_id": py2_case["case_id"],
                "classification": classification,
                "detail": detail,
                "py2_result": py2_case.get("result"),
                "py3_result": py3_case.get("result"),
            }
        )
    return out
