"""
orchestrator/verify.py

Main entrypoint. For every function in manifest/functions.json:
  1. load its frozen fixture file (fixtures/<name>.json - already generated,
     NOT regenerated here - see fixture_gen.py)
  2. run it in the py2 sandbox and the py3 sandbox
  3. classify every case as match / mismatch / ambiguous
  4. write a report to reports/verification_report.json + .md

Exit code is non-zero if ANY case across ANY function is mismatch or
ambiguous - this is what CI checks to decide green/red.

Run manually (after `python orchestrator/fixture_gen.py` at least once):
    python orchestrator/verify.py
"""

import json
import os
import sys

from docker_manager import build_images, run_in_container, IMAGE_PY2, IMAGE_PY3
from classifier import classify_function

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST_PATH = os.path.join(ROOT, "manifest", "functions.json")
FIXTURES_DIR = os.path.join(ROOT, "fixtures")
REPORTS_DIR = os.path.join(ROOT, "reports")


def load_manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)["functions"]


def run_function(func_spec):
    name = func_spec["name"]
    fixture_path = os.path.abspath(os.path.join(FIXTURES_DIR, "{0}.json".format(name)))
    if not os.path.exists(fixture_path):
        raise FileNotFoundError(
            "No fixture file for '{0}'. Run orchestrator/fixture_gen.py first.".format(name)
        )

    py2_run = run_in_container(IMAGE_PY2, fixture_path, func_spec["legacy_module"], name)
    py3_run = run_in_container(IMAGE_PY3, fixture_path, func_spec["new_module"], name)

    if py2_run["error"] or py3_run["error"]:
        return {
            "function": name,
            "status": "infra_error",
            "detail": {"py2_error": py2_run["error"], "py3_error": py3_run["error"]},
            "cases": [],
        }

    cases = classify_function(name, py2_run["results"], py3_run["results"])
    counts = {"match": 0, "mismatch": 0, "ambiguous": 0}
    for c in cases:
        counts[c["classification"]] += 1

    status = "pass" if counts["mismatch"] == 0 and counts["ambiguous"] == 0 else "fail"
    return {"function": name, "status": status, "counts": counts, "cases": cases}


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    build_images(repo_root=ROOT)

    functions = load_manifest()
    report = {"functions": []}
    overall_ok = True

    for func_spec in functions:
        result = run_function(func_spec)
        report["functions"].append(result)
        if result["status"] != "pass":
            overall_ok = False
        print("{0}: {1}".format(result["function"], result["status"].upper()))

    with open(os.path.join(REPORTS_DIR, "verification_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    write_markdown_report(report)

    if not overall_ok:
        print("\nVerification FAILED - see reports/verification_report.md for details.")
        sys.exit(1)
    print("\nAll functions verified: match on every case.")


def write_markdown_report(report):
    lines = ["# Verification Report\n"]
    for func in report["functions"]:
        lines.append("## {0} - {1}\n".format(func["function"], func["status"].upper()))
        if func["status"] == "infra_error":
            lines.append("Infrastructure error: `{0}`\n".format(func["detail"]))
            continue
        lines.append(
            "match: {0} | mismatch: {1} | ambiguous: {2}\n".format(
                func["counts"]["match"], func["counts"]["mismatch"], func["counts"]["ambiguous"]
            )
        )
        for c in func["cases"]:
            if c["classification"] != "match":
                lines.append(
                    "- case {0}: **{1}** - py2={2!r} py3={3!r} - {4}\n".format(
                        c["case_id"], c["classification"], c["py2_result"], c["py3_result"], c["detail"]
                    )
                )
    with open(os.path.join(REPORTS_DIR, "verification_report.md"), "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    main()
