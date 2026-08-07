"""
tests/test_fixture_gen.py
Run with: python tests/test_fixture_gen.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.fixture_gen import generate_cases_for_function  # noqa: E402


def test_range_override_is_respected():
    func_spec = {
        "name": "apply_discount",
        "args": [
            {"name": "price", "type": "float", "range": [0, 1000]},
            {"name": "discount_percent", "type": "int", "range": [0, 100]},
        ],
    }
    cases = generate_cases_for_function(func_spec, n=20)
    # generated (non-boundary) cases should respect the range
    generated = cases[:20]
    for c in generated:
        price, discount = c["args"]
        assert 0 <= price <= 1000, price
        assert 0 <= discount <= 100, discount


def test_boundary_cases_included():
    func_spec = {
        "name": "normalize_name",
        "args": [{"name": "raw_name", "type": "str"}],
    }
    cases = generate_cases_for_function(func_spec, n=3)
    args_only = [c["args"][0] for c in cases]
    assert "" in args_only, "empty string boundary case missing"


def test_boundary_cases_respect_range():
    # Boundary values (e.g. -1 from BOUNDARY_VALUES) must be clamped into the
    # manifest's per-argument range, so out-of-domain inputs aren't generated.
    func_spec = {
        "name": "apply_discount",
        "args": [
            {"name": "price", "type": "float", "range": [0, 1000]},
            {"name": "discount_percent", "type": "int", "range": [0, 100]},
        ],
    }
    cases = generate_cases_for_function(func_spec, n=3)
    for c in cases:
        price, discount = c["args"]
        assert 0 <= price <= 1000, price
        assert 0 <= discount <= 100, discount


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
