"""
orchestrator/docker_manager.py

Thin wrapper around the plain `docker` CLI (via subprocess) - not docker-py,
not docker-compose. This is an imperative "run N different one-off
containers" workload, not a static service topology, so the CLI loop is
simpler to write, debug, and explain live than either alternative.
"""

import json
import os
import subprocess

IMAGE_PY2 = "verify-py2:latest"
IMAGE_PY3 = "verify-py3:latest"

DEFAULT_TIMEOUT = 30  # seconds, per container run


def build_images(repo_root="."):
    """Build both sandbox images once. Call this before any run_in_container."""
    repo_root = os.path.abspath(repo_root)
    for image, dockerfile_rel in [
        (IMAGE_PY2, "harness/Dockerfile.py2"),
        (IMAGE_PY3, "harness/Dockerfile.py3"),
    ]:
        dockerfile = os.path.join(repo_root, dockerfile_rel)
        cmd = ["docker", "build", "-f", dockerfile, "-t", image, repo_root]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "docker build failed for {0}:\n{1}".format(image, result.stderr)
            )
        print("Built {0}".format(image))


def run_in_container(image, fixture_file_abs_path, module_path, func_name, timeout=DEFAULT_TIMEOUT):
    """
    Runs the harness inside an isolated container against a fixture file.
    Returns the parsed JSON result list, or a synthetic error entry on
    timeout / crash so a single bad function never kills the whole batch.
    """
    cmd = [
        "docker", "run", "--rm",
        "--network=none",
        "--memory=256m",
        "--cpus=1",
        "-v", "{0}:/fixtures.json:ro".format(fixture_file_abs_path),
        image,
        "/fixtures.json", module_path, func_name,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout after {0}s".format(timeout), "results": None}

    if result.returncode != 0:
        return {"error": "container exited non-zero: {0}".format(result.stderr.strip()), "results": None}

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "harness produced non-JSON output: {0}".format(result.stdout[:500]), "results": None}

    return {"error": None, "results": parsed}
