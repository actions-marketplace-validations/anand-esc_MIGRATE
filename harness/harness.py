# harness/harness.py
#
# Runs INSIDE the sandbox container (py2 or py3). Never runs on the host.
# Usage: python harness.py <fixture_json_path> <module_path> <function_name>
#
# Prints a single JSON array to stdout:
#   [{"case_id": 0, "result": ..., "type": "...", "error": null}, ...]
#
# Any exception raised by the target function is caught per-case so one
# bad input never takes down the whole batch.

import json
import sys
import importlib


def run():
    if len(sys.argv) != 4:
        sys.stderr.write(
            "usage: harness.py <fixture_json_path> <module_path> <function_name>\n"
        )
        sys.exit(2)

    fixture_path, module_path, func_name = sys.argv[1], sys.argv[2], sys.argv[3]

    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)

    with open(fixture_path) as f:
        cases = json.load(f)["cases"]

    results = []
    for i, case in enumerate(cases):
        args = case.get("args", [])
        kwargs = case.get("kwargs", {})
        try:
            r = func(*args, **kwargs)
            results.append(
                {
                    "case_id": i,
                    "result": r,
                    "type": type(r).__name__,
                    "error": None,
                }
            )
        except Exception as e:  # noqa: BLE001 - intentional: catch everything per-case
            results.append(
                {
                    "case_id": i,
                    "result": None,
                    "type": None,
                    "error": "{0}: {1}".format(type(e).__name__, e),
                }
            )

    sys.stdout.write(json.dumps(results))


if __name__ == "__main__":
    run()
