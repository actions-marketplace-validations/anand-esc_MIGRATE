# AI Agent Task Breakdown

This document outlines the step-by-step task execution plan that the MIGRATE AI pipeline (orchestrated via `legacy-pyconvert`) works through during a typical migration run.

## Stage 1: Codebase Research & Classification
- **Actor:** Classifier Agent (`agents/classifier`)
- **Action:** Scans the target directory for Python source files.
- **Task:** Uses Abstract Syntax Tree (AST) parsing and heuristics to break down the codebase into atomic, top-level functions.
- **Result:** Groups functions into three operational queues:
  - `template_match`: Routine migrations (standard library renames, basic syntax).
  - `llm_needed`: Deep logic migrations requiring reasoning (string/bytes dichotomy, generator refactoring).
  - `unsupported`: Complex metaprogramming that cannot be safely translated automatically.

## Stage 2: Conversion & Translation
- **Actor:** Converter Agent (`agents/converter_critic`)
- **Action:** Iterates through the operational queues.
- **Task:** 
  - For `template_match` items, applies the regex template engine for rapid, zero-hallucination translation.
  - For `llm_needed` items, delegates to a specialized language model prompt to safely refactor standard library usage while maintaining logical flow.
- **Result:** Produces a translated Python 3 candidate for the original function.

## Stage 3: Sandboxed Verification (The Critical Gate)
- **Actor:** Verifier Agent (`agents/verifier`)
- **Action:** Executes the Hypothesis fuzzing engine.
- **Task:** 
  - Spins up a `python:2.7-slim` container to run the original code with generated fixtures.
  - Spins up a `python:3.12-slim` container to run the candidate code with the exact same fixtures.
  - Compares standard outputs and structural returns using `DeepDiff`.
- **Result:** Returns `exact_match`, `clear_mismatch`, or `ambiguous` (needs review).

## Stage 4: Reporting and Auto-Commit
- **Actor:** CLI Orchestrator (`cli/convert.py`)
- **Action:** Consolidates all verdicts.
- **Task:** Generates a unified `summary.json`. Overwrites original files with migrated code if verification succeeded.
- **Result:** Commits passing code to the repo and surfaces failed/ambiguous code via GitHub PR annotations.
