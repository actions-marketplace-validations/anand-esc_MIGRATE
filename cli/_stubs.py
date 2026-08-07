"""Day-1 stand-ins for the three teammates' modules.

STUB-FIRST: cli/convert.py must be runnable and CI must be green before any
real classifier/converter/verifier code exists. convert.py tries the real
imports first and falls back to these stubs -- see cli/convert.py's
`_load_backends()`. As each module lands, delete the corresponding stub
usage by making the real import succeed; no changes to convert.py's control
flow should be needed.

Expected real import paths (confirm/adjust with each owner as their module
lands -- these are Agent D's best guess from the brief, not dictated):

  Om        agents.classifier.classify_source(path: str) -> list[ClassifiedFunction]
  Suryansh  agents.converter_critic.graph.run(fn: ClassifiedFunction) -> ConversionResult   (confirmed by brief)
  Pritam    agents.verifier.verify_function(original: str, converted: str,
                function_name: str) -> VerificationResult

These stubs deliberately do *real, if crude* work instead of returning
hardcoded constants, so that a demo run against them produces a believable
mix of pass/fail/needs-review instead of an all-green rubber stamp that
would hide bugs in convert.py's routing logic.
"""

from __future__ import annotations

import ast
import re
from typing import List

from shared.schemas import (
    ClassifiedFunction,
    ConversionResult,
    VerificationResult,
    VerifierVerdict,
)

_DEF_RE = re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE)

_UNSUPPORTED_MARKERS = ("exec ", "exec(", "__metaclass__")
_LLM_NEEDED_MARKERS = (
    "unicode(",
    "_is_unicode",
    "xrange(256)",
    "bytearray(xrange",
    "isinstance(v, str)",
)
_RAISE3_RE = re.compile(r"raise\s+\w+(\.\w+)*\s*,\s*.+,\s*\w+\s*$", re.MULTILINE)


def stub_classify_source(path: str) -> List[ClassifiedFunction]:
    """Crude stand-in for Om's ast/lib2to3-based classifier.

    Splits the file into top-level `def name(...)` blocks by regex (real
    classifier will use ast/lib2to3 and handle nesting, decorators, etc.)
    and tags each with a regex heuristic over its source text.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    matches = list(_DEF_RE.finditer(text))
    functions: List[ClassifiedFunction] = []
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        source = text[start:end].rstrip() + "\n"
        lineno = text.count("\n", 0, start) + 1

        if any(marker in source for marker in _UNSUPPORTED_MARKERS):
            classification = "unsupported"
        elif _RAISE3_RE.search(source) or any(
            marker in source for marker in _LLM_NEEDED_MARKERS
        ):
            classification = "llm_needed"
        else:
            classification = "template_match"

        functions.append(
            ClassifiedFunction(
                function_id=name,
                source_code=source,
                file_path=path,
                lineno=lineno,
                classification=classification,
                py2_constructs=[],
            )
        )
    return functions


_TEMPLATE_FIXES = [
    (re.compile(r"\bxrange\s*\("), "range("),
    (re.compile(r"\.iteritems\s*\(\s*\)"), ".items()"),
    (re.compile(r"\.iterkeys\s*\(\s*\)"), ".keys()"),
    (re.compile(r"\.itervalues\s*\(\s*\)"), ".values()"),
    (re.compile(r"\.has_key\s*\(\s*([^)]*)\)"), r" in \1"),  # best-effort, order-sensitive
    (re.compile(r"^(\s*)print\s+([^\(\n#]+)", re.MULTILINE), r"\1print(\2)"),
    (re.compile(r"except\s+([a-zA-Z0-9_\.]+|\([^)]+\))\s*,\s*([a-zA-Z0-9_]+)\s*:"), r"except \1 as \2:"),
    (re.compile(r"([^\s<]+)\s*<>\s*([^\s>]+)"), r"\1 != \2"),
    (re.compile(r"^(\s*)raise\s+([a-zA-Z0-9_\.]+)\s*,\s*([^\n#]+)", re.MULTILINE), r"\1raise \2(\3)"),
    (re.compile(r"`([^`]+)`"), r"repr(\1)"),
    (re.compile(r"\b(\d+)L\b"), r"\1"),
    (re.compile(r"\b0([0-7]+)\b"), r"0o\1"),
]


def stub_run(fn: ClassifiedFunction) -> ConversionResult:
    """Crude stand-in for Suryansh's agents.converter_critic.graph.run()."""
    if fn.classification == "unsupported":
        return ConversionResult(
            function_id=fn.function_id,
            converted_code=None,
            critic_verdict="conversion_failed",
            critic_notes="classified unsupported; stub converter does not attempt a conversion",
            tokens_used=0,
        )

    converted = fn.source_code
    for pattern, replacement in _TEMPLATE_FIXES:
        converted = pattern.sub(replacement, converted)

    if fn.classification == "llm_needed":
        return ConversionResult(
            function_id=fn.function_id,
            converted_code=converted,
            critic_verdict="leftover_py2_syntax",
            critic_notes="stub converter applied mechanical fixes only; this function needs a real LLM pass",
            tokens_used=10,
        )

    return ConversionResult(
        function_id=fn.function_id,
        converted_code=converted,
        critic_verdict="clean",
        critic_notes=None,
        tokens_used=10,
    )


_PY2_LEFTOVER_MARKERS = (
    "xrange(",
    ".iteritems(",
    ".iterkeys(",
    ".itervalues(",
    ".has_key(",
    "print ",
)


def stub_verify_function(
    original: str, converted: str, function_name: str
) -> VerificationResult:
    """Crude stand-in for Pritam's sandbox-diff verifier.

    Real verifier runs both versions in python:2.7-slim / python:3.12-slim
    containers against generated fixtures and diffs outputs. The stub can't
    do that on Day 1, so it does the cheapest real check available: does
    the converted source actually parse as Python 3, and does it still
    contain leftover Python-2-only syntax. This is intentionally NOT a
    rubber stamp -- it can and does produce clear_mismatch/ambiguous.
    """
    try:
        ast.parse(converted)
    except SyntaxError as e:
        return VerificationResult(
            function_name=function_name,
            verdict=VerifierVerdict.CLEAR_MISMATCH,
            details=f"converted source does not parse as Python 3: {e}",
            fixture_count=0,
        )

    leftovers = [m for m in _PY2_LEFTOVER_MARKERS if m in converted]
    if leftovers:
        return VerificationResult(
            function_name=function_name,
            verdict=VerifierVerdict.AMBIGUOUS,
            details=f"converted source parses but still contains py2-only markers: {leftovers}",
            fixture_count=0,
        )

    return VerificationResult(
        function_name=function_name,
        verdict=VerifierVerdict.EXACT_MATCH,
        details="stub check only: parses cleanly with no leftover py2 markers (no real sandbox diff yet)",
        fixture_count=0,
    )
