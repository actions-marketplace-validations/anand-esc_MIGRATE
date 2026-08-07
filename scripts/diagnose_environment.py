"""
scripts/diagnose_environment.py

Run this from the SAME terminal/shell you used to `pip install` the
dependencies:

    python scripts/diagnose_environment.py

Then compare its output against what your IDE reports. This pinpoints the
single most common cause of "installed but still shows unresolved import"
in VS Code / Cursor / PyCharm: the IDE's language server is pointing at a
DIFFERENT Python interpreter than the one packages were installed into.

If sys.executable here does NOT match the interpreter path your IDE has
selected (Cmd/Ctrl+Shift+P -> "Python: Select Interpreter" in VS Code or
Cursor), that mismatch is the root cause - not a code problem, and not a
missing package.
"""

import sys
import os
import subprocess


def check(label, fn):
    print("\n--- {0} ---".format(label))
    try:
        fn()
    except Exception as e:
        print("  ERROR: {0}".format(e))


def show_interpreter():
    print("  sys.executable : {0}".format(sys.executable))
    print("  sys.version    : {0}".format(sys.version.split()[0]))
    print("  sys.prefix     : {0}".format(sys.prefix))
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print("  in a venv?     : {0}".format(in_venv))
    if not in_venv:
        print(
            "  NOTE: not running inside a virtual environment. If your IDE "
            "expects one (a .venv/ folder, conda env, etc.) and none exists, "
            "that mismatch alone explains unresolved imports."
        )


def show_package_locations():
    for pkg in ("hypothesis", "deepdiff"):
        try:
            mod = __import__(pkg)
            print("  {0:12s} version={1:10s} location={2}".format(
                pkg, getattr(mod, "__version__", "?"), os.path.dirname(mod.__file__)
            ))
        except ImportError as e:
            print("  {0:12s} NOT IMPORTABLE from this interpreter: {1}".format(pkg, e))


def show_pip_locations():
    for pkg in ("hypothesis", "deepdiff"):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("  {0}: not found via `{1} -m pip show`".format(pkg, sys.executable))
            continue
        for line in result.stdout.splitlines():
            if line.startswith("Location:") or line.startswith("Version:"):
                print("  {0}: {1}".format(pkg, line))


def show_docker_status():
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  Docker daemon: reachable")
        else:
            print("  Docker daemon: CLI found but NOT reachable")
            print("  {0}".format(result.stderr.strip()[:300]))
    except FileNotFoundError:
        print("  `docker` command not found on PATH")
    except subprocess.TimeoutExpired:
        print("  `docker info` timed out - daemon likely not running")


def show_wsl_hint():
    if os.name == "nt":
        print("  Running natively on Windows.")
        print(
            "  If Docker is used via WSL2, and packages were pip-installed "
            "INSIDE a WSL shell, a Windows-side IDE window won't see them. "
            "In VS Code/Cursor: use the 'WSL' remote connection (green icon, "
            "bottom-left) to open this project, not a native Windows window."
        )
    elif "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False:
        print("  Running inside WSL.")
        print(
            "  If your IDE window is NOT connected via the WSL remote "
            "extension, it is analyzing this code with a Windows-side "
            "interpreter that cannot see packages installed here."
        )
    else:
        print("  Not Windows/WSL - not a likely factor here.")


if __name__ == "__main__":
    print("=" * 60)
    print("Environment diagnostic - fixture_verifier")
    print("=" * 60)
    check("Python interpreter (THIS is what your IDE must match)", show_interpreter)
    check("Package import check (direct)", show_package_locations)
    check("Package location (via pip show)", show_pip_locations)
    check("Docker daemon reachability", show_docker_status)
    check("Windows/WSL cross-environment hint", show_wsl_hint)
    print("\n" + "=" * 60)
    print("Next step: open your IDE, run 'Python: Select Interpreter', and")
    print("confirm the selected path matches sys.executable printed above.")
    print("=" * 60)
