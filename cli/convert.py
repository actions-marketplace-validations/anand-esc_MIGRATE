"""legacy-pyconvert -- CLI orchestration for Deploy or Die.

Wires together (but does not implement):
  Om        classifier          -> shared.schemas.ClassifiedFunction
  Suryansh  converter + critic  -> agents.converter_critic.graph.run(fn)
  Pritam    verifier            -> sandboxed original-vs-converted diff

Core non-negotiable baked into this file's control flow (not just docs):
NEVER report a function as passing unless Pritam's verifier itself
returned exact_match AND Suryansh's critic approved it outright. See
`_resolve_status()` for the single place this decision is made -- every
other function funnels through it, so there is exactly one place in the
codebase that can mark something a PASS.

See ARCHITECTURE.md for the full status-mapping table and the rationale,
and AGENTS.md for the rules this file exists to enforce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import click

from shared.schemas import (
    ClassifiedFunction,
    ConversionResult,
    FunctionOutcome,
    PipelineStatus,
    VerificationResult,
    VerifierVerdict,
)

# ---------------------------------------------------------------------------
# Backend loading: real module if it's landed, stub otherwise. This is the
# ONLY place that decides real-vs-stub -- nothing below this block knows or
# cares which one it's calling.
# ---------------------------------------------------------------------------
BACKEND_STATUS = {}

try:
    from agents.classifier import classify_source as _classify_source  # type: ignore

    BACKEND_STATUS["classifier"] = "real (agents.classifier)"
except ImportError:
    from cli._stubs import stub_classify_source as _classify_source

    BACKEND_STATUS["classifier"] = "stub"

try:
    from agents.converter_critic.graph import run as _run_converter  # type: ignore

    BACKEND_STATUS["converter_critic"] = "real (agents.converter_critic.graph)"
except ImportError:
    from cli._stubs import stub_run as _run_converter

    BACKEND_STATUS["converter_critic"] = "stub"

try:
    from agents.verifier import verify_function as _verify_function  # type: ignore

    BACKEND_STATUS["verifier"] = "real (agents.verifier)"
except ImportError:
    from cli._stubs import stub_verify_function as _verify_function

    BACKEND_STATUS["verifier"] = "stub"


def _report_backends():
    for name, status in BACKEND_STATUS.items():
        marker = "REAL" if status.startswith("real") else "STUB"
        click.echo(f"  [{marker}] {name}: {status}", err=True)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def _discover_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p
        for p in target.rglob("*.py")
        if "__pycache__" not in p.parts
    )


# ---------------------------------------------------------------------------
# The single status-resolution function. Every function's final
# PipelineStatus is decided HERE and nowhere else.
# ---------------------------------------------------------------------------
def _resolve_status(
    critic_verdict: Optional[str],
    verifier_verdict: Optional[VerifierVerdict],
) -> PipelineStatus:
    # conversion_failed (or any missing conversion) is a hard FAIL. It must
    # never reach here with a verifier_verdict attached -- callers enforce
    # that by never calling the verifier in this case (see run_pipeline).
    if critic_verdict == "conversion_failed":
        return PipelineStatus.FAIL

    if verifier_verdict is None:
        # Shouldn't happen for any critic_verdict other than
        # CONVERSION_FAILED -- treat defensively as needs-review rather
        # than silently passing.
        return PipelineStatus.NEEDS_REVIEW

    if verifier_verdict == VerifierVerdict.CLEAR_MISMATCH:
        return PipelineStatus.FAIL

    if verifier_verdict == VerifierVerdict.AMBIGUOUS:
        return PipelineStatus.NEEDS_REVIEW

    # verifier_verdict == EXACT_MATCH from here on.
    if critic_verdict == "clean":
        return PipelineStatus.PASS

    # Critic flagged this function for human review even though the
    # sandbox diff came back clean. The sandbox result is real signal, but
    # a critic concern is never silently discarded -- cap at needs-review
    # rather than reporting a full pass.
    return PipelineStatus.NEEDS_REVIEW


def _run_one_function(fn: ClassifiedFunction) -> FunctionOutcome:
    if fn.classification == "unsupported":
        return FunctionOutcome(
            function_name=fn.function_id,
            file_path=fn.file_path,
            classification=fn.classification,
            status=PipelineStatus.FAIL,
            critic_verdict=None,
            verifier_verdict=None,
            detail=f"classified unsupported: py2_constructs={fn.py2_constructs}",
        )

    if fn.classification == "template_match":
        # Rule: Never call the LLM for a function that isn't classified llm_needed.
        # Template-matched functions are converted by the local template engine only.
        from cli._stubs import stub_run
        result: ConversionResult = stub_run(fn)
    else:
        result: ConversionResult = _run_converter(fn)

    if result.critic_verdict == "conversion_failed":
        # Non-negotiable: Pritam's verifier NEVER receives a function whose
        # conversion outright failed. No converted_source to sandbox-diff
        # anyway -- there is nothing meaningful to verify.
        return FunctionOutcome(
            function_name=fn.function_id,
            file_path=fn.file_path,
            classification=fn.classification,
            status=PipelineStatus.FAIL,
            critic_verdict=result.critic_verdict,
            verifier_verdict=None,
            detail=result.critic_notes or "conversion_failed",
        )

    verifier_result: VerificationResult = _verify_function(
        fn.source_code, result.converted_code or "", fn.function_id
    )

    status = _resolve_status(result.critic_verdict, verifier_result.verdict)

    return FunctionOutcome(
        function_name=fn.function_id,
        file_path=fn.file_path,
        classification=fn.classification,
        status=status,
        critic_verdict=result.critic_verdict,
        verifier_verdict=verifier_result.verdict,
        detail=verifier_result.details or result.critic_notes,
        converted_code=result.converted_code,
    )


def _run_pipeline(target: Path, files: List[Path], out_dir: Path) -> List[FunctionOutcome]:
    outcomes: List[FunctionOutcome] = []
    
    migrated_dir = Path("migrated")
    migrated_dir.mkdir(parents=True, exist_ok=True)
    
    for path in files:
        functions = _classify_source(str(path))
        file_content = path.read_text(encoding="utf-8")
        has_changes = False
        
        for fn in functions:
            outcome = _run_one_function(fn)
            outcomes.append(outcome)
            
            # Only replace if conversion succeeded and didn't outright fail verification
            if outcome.converted_code and outcome.status != PipelineStatus.FAIL:
                file_content = file_content.replace(fn.source_code, outcome.converted_code, 1)
                has_changes = True

        # Apply module-level fixes for things outside functions (like imports)
        from cli._stubs import _TEMPLATE_FIXES
        for pattern, replacement in _TEMPLATE_FIXES:
            new_content = pattern.sub(replacement, file_content)
            if new_content != file_content:
                file_content = new_content
                has_changes = True

        if has_changes:
            if target.is_dir():
                try:
                    rel_path = path.relative_to(target)
                except ValueError:
                    rel_path = path.name
            else:
                rel_path = Path(path.name)
                
            dest = migrated_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(file_content, encoding="utf-8")
                
    return outcomes


def _write_summary(out_dir: Path, target: str, outcomes: List[FunctionOutcome]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"pass": 0, "fail": 0, "needs_review": 0}
    for o in outcomes:
        counts[o.status.value] += 1
    summary = {
        "target_path": target,
        "counts": {**counts, "total": len(outcomes)},
        "functions": [o.model_dump(mode="json") for o in outcomes],
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _print_human_summary(summary: dict):
    counts = summary["counts"]
    click.echo("")
    click.echo(f"  pass:         {counts['pass']}")
    click.echo(f"  needs_review: {counts['needs_review']}")
    click.echo(f"  fail:         {counts['fail']}")
    click.echo(f"  total:        {counts['total']}")
    click.echo("")
    for fn in summary["functions"]:
        marker = {"pass": "PASS", "fail": "FAIL", "needs_review": "REVIEW"}[fn["status"]]
        click.echo(f"  [{marker:>6}] {fn['function_name']}  ({fn['classification']})")
        if fn.get("detail"):
            click.echo(f"           {fn['detail']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@click.group()
def cli():
    """legacy-pyconvert: convert legacy Python 2 code to Python 3 and prove
    behavioral equivalence via sandboxed diffing."""


@cli.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("build"), show_default=True)
@click.option(
    "--fail-on-mismatch/--no-fail-on-mismatch",
    default=True,
    show_default=True,
    help="Exit non-zero if any function comes back as a clear mismatch (fail).",
)
def convert(target: Path, out_dir: Path, fail_on_mismatch: bool):
    """Run the full pipeline: classify -> convert/critic -> verify.

    TARGET is a file or directory of Python 2 source.
    """
    click.echo(f"legacy-pyconvert convert {target}", err=True)
    _report_backends()

    files = _discover_files(target)
    if not files:
        click.echo(f"No .py files found under {target}", err=True)
        sys.exit(2)

    outcomes = _run_pipeline(target, files, out_dir)
    summary = _write_summary(out_dir, str(target), outcomes)
    _print_human_summary(summary)

    click.echo(f"\nwrote {out_dir / 'summary.json'}", err=True)

    if fail_on_mismatch and summary["counts"]["fail"] > 0:
        sys.exit(1)
    sys.exit(0)


@cli.command()
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("build"), show_default=True)
@click.option("--fail-on-mismatch/--no-fail-on-mismatch", default=True, show_default=True)
def verify(out_dir: Path, fail_on_mismatch: bool):
    """Re-print pass/fail status from an existing build/summary.json and
    apply --fail-on-mismatch exit-code semantics.

    Useful in CI to gate on a summary.json produced by a separate
    `convert` invocation without re-running classification/conversion.
    """
    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        click.echo(f"{summary_path} not found -- run `convert` first", err=True)
        sys.exit(2)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _print_human_summary(summary)

    if fail_on_mismatch and summary["counts"]["fail"] > 0:
        sys.exit(1)
    sys.exit(0)


@cli.command()
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("build"), show_default=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "github"]),
    default="text",
    show_default=True,
    help="'github' emits GitHub Actions job-summary markdown (for $GITHUB_STEP_SUMMARY).",
)
def report(out_dir: Path, fmt: str):
    """Print a human-readable summary from build/summary.json."""
    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        click.echo(f"{summary_path} not found -- run `convert` first", err=True)
        sys.exit(2)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    counts = summary["counts"]

    if fmt == "text":
        _print_human_summary(summary)
        return

    lines = [
        "## Deploy or Die -- conversion report",
        "",
        f"Target: `{summary['target_path']}`",
        "",
        "| status | count |",
        "|---|---|",
        f"| PASS | {counts['pass']} |",
        f"| NEEDS REVIEW | {counts['needs_review']} |",
        f"| FAIL | {counts['fail']} |",
        f"| total | {counts['total']} |",
        "",
        "| function | classification | status | detail |",
        "|---|---|---|---|",
    ]
    for fn in summary["functions"]:
        detail = (fn.get("detail") or "").replace("|", "\\|").replace("\n", " ")
        status_label = fn["status"].replace("_", " ").upper()
        lines.append(
            f"| `{fn['function_name']}` | {fn['classification']} | {status_label} | {detail} |"
        )
    click.echo("\n".join(lines))


if __name__ == "__main__":
    cli()
