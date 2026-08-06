"""
tests/test_classifier.py
Run with: python -m pytest tests/test_classifier.py -v
(or plain: python tests/test_classifier.py)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.classifier import classify_case, classify_function  # noqa: E402


def case(result=None, type_=None, error=None, case_id=0):
    return {"case_id": case_id, "result": result, "type": type_, "error": error}


def test_identical_values_match():
    c, detail = classify_case(case(result=100.0), case(result=100.0))
    assert c == "match", detail


def test_int_vs_float_same_value_matches():
    c, detail = classify_case(case(result=5), case(result=5.0))
    assert c == "match", detail


def test_genuine_value_difference_is_mismatch():
    c, detail = classify_case(case(result=10.05), case(result=10.0))
    assert c == "mismatch", detail


def test_one_side_errors_is_mismatch():
    c, detail = classify_case(
        case(error="KeyError: price"), case(result=250.0)
    )
    assert c == "mismatch", detail


def test_both_error_same_type_matches():
    c, detail = classify_case(
        case(error="ZeroDivisionError: division by zero"),
        case(error="ZeroDivisionError: float division by zero"),
    )
    assert c == "match", detail


def test_both_error_different_type_is_ambiguous():
    c, detail = classify_case(
        case(error="ZeroDivisionError: division by zero"),
        case(error="ValueError: bad input"),
    )
    assert c == "ambiguous", detail


def test_str_unicode_style_values_match():
    # By the time results reach the classifier they're already plain JSON
    # strings (JSON has no separate unicode/str/bytes distinction), so
    # this is mostly a regression guard rather than a real-world gap.
    c, detail = classify_case(case(result="John Doe"), case(result="John Doe"))
    assert c == "match", detail


def test_structural_difference_is_ambiguous_not_mismatch():
    c, detail = classify_case(
        case(result={"a": 1}), case(result={"a": 1, "b": 2})
    )
    assert c == "ambiguous", detail


def test_classify_function_mismatched_lengths_raises():
    try:
        classify_function("f", [case()], [case(), case(case_id=1)])
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, "-", e)
    print("\n{0}/{1} passed".format(len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
