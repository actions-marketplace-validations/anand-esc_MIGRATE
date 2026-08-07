"""
orchestrator/fixture_gen.py

Runs on the HOST (Python 3.12), never inside a sandbox container.
Reads manifest/functions.json, uses hypothesis to draw diverse inputs per
function, adds explicit boundary cases, and freezes everything to
fixtures/<function_name>.json.

Fixtures are generated ONCE and committed to the repo. CI does not
regenerate them - it only reuses the frozen file, so every run is
comparing against the exact same inputs.

Run manually:
    python orchestrator/fixture_gen.py
"""

import json
import os
import warnings
from hypothesis import strategies as st

warnings.filterwarnings("ignore", message=".*non-interactive.*")

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "manifest", "functions.json")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

N_GENERATED_CASES = 6  # per function, on top of explicit boundary cases

# Map manifest type strings -> hypothesis strategies.
# Extend this as new argument shapes show up in the real manifest.
TYPE_STRATEGIES = {
    "int": st.integers(min_value=-1000, max_value=1000),
    "float": st.floats(
        min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False
    ),
    "str": st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=30),
    "list[dict]": st.lists(
        st.fixed_dictionaries(
            {
                "price": st.floats(
                    min_value=0, max_value=500, allow_nan=False, allow_infinity=False
                ),
                "qty": st.integers(min_value=0, max_value=20),
            }
        ),
        min_size=0,
        max_size=5,
    ),
}

# Explicit boundary values per type, always included regardless of what
# hypothesis draws. This is the "custom type-informed" fallback layer -
# cheap, deterministic, and catches the edge cases random draws often miss.
BOUNDARY_VALUES = {
    "int": [0, -1, 1],
    "float": [0.0, -1.0],
    "str": ["", " "],
    "list[dict]": [[], [{"price": 0.0, "qty": 0}]],
}


def strategy_for(arg_spec):
    arg_type = arg_spec["type"]
    if arg_type not in TYPE_STRATEGIES:
        raise ValueError(
            "No strategy registered for type '{0}'. Add one to TYPE_STRATEGIES "
            "in fixture_gen.py.".format(arg_type)
        )
    # Optional per-argument range override in the manifest, e.g.:
    #   {"name": "discount_percent", "type": "int", "range": [0, 100]}
    # Falls back to the generic type strategy if no range is given.
    if "range" in arg_spec and arg_type in ("int", "float"):
        lo, hi = arg_spec["range"]
        return st.integers(min_value=lo, max_value=hi) if arg_type == "int" \
            else st.floats(min_value=lo, max_value=hi, allow_nan=False, allow_infinity=False)
    return TYPE_STRATEGIES[arg_type]


def generate_cases_for_function(func_spec, n=N_GENERATED_CASES, seed=42):
    arg_specs = func_spec["args"]
    arg_types = [a["type"] for a in arg_specs]

    # Random-ish generated cases (fixed seed keeps a single generation run
    # reproducible; since output is frozen to JSON, this only matters the
    # moment you (re)generate fixtures, not on every CI run).
    import random

    random.seed(seed)
    generated = []
    for _ in range(n):
        args = [strategy_for(a).example() for a in arg_specs]
        generated.append({"args": args})

    # Explicit boundary combinations: pair up the first boundary value for
    # each argument position, plus a full boundary sweep for single-arg
    # functions. Keeps this simple rather than a full cartesian product,
    # which would blow up fast for multi-arg functions.
    #
    # Boundary values are clamped to the manifest's per-argument "range"
    # hint when present. Without this, e.g. a numeric arg scoped to [0,100]
    # would still get boundary inputs like -1 (from BOUNDARY_VALUES),
    # producing out-of-domain fixtures that the real code would never see.
    boundary_cases = []
    max_boundaries = max(len(BOUNDARY_VALUES[t]) for t in arg_types)
    for i in range(max_boundaries):
        args = []
        for spec, t in zip(arg_specs, arg_types):
            values = BOUNDARY_VALUES[t]
            value = values[i] if i < len(values) else values[-1]
            args.append(_clamp_to_range(value, spec))
        boundary_cases.append({"args": args})

    return generated + boundary_cases


def _clamp_to_range(value, arg_spec):
    """Clamp a numeric boundary value into the manifest's range, if present."""
    if "range" not in arg_spec or arg_spec["type"] not in ("int", "float"):
        return value
    lo, hi = arg_spec["range"]
    return max(lo, min(hi, value))


def main():
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    for func_spec in manifest["functions"]:
        cases = generate_cases_for_function(func_spec)
        out_path = os.path.join(FIXTURES_DIR, "{0}.json".format(func_spec["name"]))
        with open(out_path, "w") as f:
            json.dump({"function": func_spec["name"], "cases": cases}, f, indent=2)
        print("Wrote {0} cases -> {1}".format(len(cases), out_path))


if __name__ == "__main__":
    main()
