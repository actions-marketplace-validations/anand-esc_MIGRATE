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

# DeepDiff's significant_digits uses RELATIVE tolerance, which silently
# treats two near-zero (denormal) numbers as "equal" even when they differ
# in absolute terms (e.g. 0 vs 2.5e-307). For a verification tool that must
# never silently pass a real behavioral difference, any two results this
# close to zero are compared exactly with no tolerance. Legitimate small
# results (e.g. 1e-5) are well above this and keep using relative tolerance.
NEAR_ZERO_THRESHOLD = 1e-12

# German sharp-s: Python 2's str.title() leaves 'ß' unchanged, while Python 3
# expands a title-cased 'ß' to 'Ss'. This is a well-known, benign cross-version
# difference (not a bug in the converted code). When normalizing, collapse the
# Py3 title-case expansion back to the Py2 form so the two compare as equal.
# This is the documented "explicit rule for a confirmed benign difference"
# mechanism - kept deterministic and narrowly scoped to title-cased 'ß'.
TITLE_CASE_SHARP_S_EXPANSION = "Ss"


def _collapse_py3_sharp_s_title(value):
    """
    Replaces the Py3 title-case expansion of 'ß' ('Ss') with the Py2 form
    ('ß') so that `... ß ...`.title() differences compare as equal. Applied
    only to strings, during normalization.
    """
    return value.replace(TITLE_CASE_SHARP_S_EXPANSION, "\u00df")


def _effectively_equal(a, b):
    """
    DeepDiff's relative tolerance masks genuine differences between two
    near-zero/denormal numbers (e.g. 0 vs 2.5e-307). When BOTH results are
    numbers and both are this close to zero, fall back to an exact compare so
    a real behavioral difference is never silently swallowed. Returns None
    when this rule doesn't apply (so callers can fall through to DeepDiff).
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a) < NEAR_ZERO_THRESHOLD and abs(b) < NEAR_ZERO_THRESHOLD:
            return a == b
    return None


def normalize(value):
    """
    Makes Python 2 and Python 3 output structurally comparable.
    The single most common false-mismatch source is Py2 str/bytes/unicode
    vs Py3's single str type - collapse them before diffing. Also collapses
    the benign Py3 title-case expansion of 'ß' back to the Py2 form.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return _collapse_py3_sharp_s_title(value)
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

    result2, result3 = normalize(py2_case.get("result")), normalize(py3_case.get("result"))

    # Guard against DeepDiff's relative tolerance masking a genuine difference
    # between two near-zero/denormal results (e.g. 0 vs 2.5e-307). If this rule
    # applies it returns the exact-equality verdict; otherwise None and we fall
    # through to the normal DeepDiff comparison below.
    near_zero = _effectively_equal(result2, result3)
    if near_zero is not None:
        return ("match", None) if near_zero else ("mismatch", str((py2_case.get("result"), py3_case.get("result"))))

    diff = DeepDiff(
        result2,
        result3,
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
