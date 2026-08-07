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


class DockerNotReachableError(RuntimeError):
    """Raised when the Docker CLI is present but the daemon isn't reachable."""


def check_docker_daemon():
    """
    Preflight check: confirms `docker` is installed AND the daemon is
    actually reachable, before attempting any build/run. Without this,
    a stopped Docker Desktop / WSL2 backend / permission issue surfaces
    as a confusing low-level error deep inside a build step instead of
    a clear, actionable message here.
    """
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        raise DockerNotReachableError(
            "`docker` command not found. Docker Engine/Desktop is not installed, "
            "or not on PATH."
        )
    except subprocess.TimeoutExpired:
        raise DockerNotReachableError(
            "`docker info` timed out. The Docker daemon is likely not running "
            "(check Docker Desktop is started, or `sudo systemctl start docker` on Linux)."
        )

    if result.returncode != 0:
        raise DockerNotReachableError(
            "Docker CLI is installed but the daemon is not reachable.\n"
            "Common causes: Docker Desktop not running, WSL2 backend not started, "
            "or (on Linux) current user not in the `docker` group.\n"
            "Raw error: {0}".format(result.stderr.strip())
        )


def _to_docker_mount_path(path):
    """
    Normalizes a host path for use in a `-v host:container` mount.
    Docker Desktop (Windows/Mac) and Docker Engine (Linux) all accept
    forward-slash paths; Windows backslash paths are converted so the
    same code works unmodified across platforms.
    """
    return os.path.abspath(path).replace(os.sep, "/")


def build_images(repo_root="."):
    """Build both sandbox images once. Call this before any run_in_container."""
    check_docker_daemon()  # fail fast with a clear message, not a buried build error
    repo_root = os.path.abspath(repo_root)
    for image, dockerfile_rel in [
        (IMAGE_PY2, "harness/Dockerfile.py2"),
        (IMAGE_PY3, "harness/Dockerfile.py3"),
    ]:
        dockerfile = os.path.join(repo_root, dockerfile_rel)
        if not os.path.exists(dockerfile):
            raise FileNotFoundError(
                "Dockerfile not found at {0}. Check repo_root is correct.".format(dockerfile)
            )
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
    mount_path = _to_docker_mount_path(fixture_file_abs_path)
    cmd = [
        "docker", "run", "--rm",
        "--network=none",
        "--memory=256m",
        "--cpus=1",
        "-v", "{0}:/fixtures.json:ro".format(mount_path),
        image,
        "/fixtures.json", module_path, func_name,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"error": "`docker` command not found on PATH", "results": None}
    except subprocess.TimeoutExpired:
        return {"error": "timeout after {0}s".format(timeout), "results": None}

    if result.returncode != 0:
        return {"error": "container exited non-zero: {0}".format(result.stderr.strip()), "results": None}

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "harness produced non-JSON output: {0}".format(result.stdout[:500]), "results": None}

    return {"error": None, "results": parsed}
