# Product Requirements Document (PRD)

## Project Overview
**MIGRATE: Legacy Python Equivalence Converter**
The goal of this project is to provide a seamless, highly automated, and perfectly verified migration path for legacy Python 2 codebases upgrading to Python 3. Unlike generic AI coding tools, MIGRATE proves behavioral equivalence using isolated Docker sandboxes and strict diffing algorithms to completely eliminate silent hallucination issues.

## User Stories & Acceptance Criteria

### Epic 1: Classification & Triage
**As a** release engineer,
**I want** to automatically parse and triage Python 2 functions,
**So that** I don't waste expensive LLM compute on simple syntactic changes.

*Acceptance Criteria:*
1. The tool must parse the input directory and isolate top-level functions.
2. The tool must use regex heuristics to classify each function into one of three buckets: `template_match`, `llm_needed`, or `unsupported`.
3. Unsupported constructs (like `exec` when unhandled) must be flagged explicitly rather than failing silently.

### Epic 2: Automated Conversion
**As a** developer,
**I want** standard Python 2 syntax (like `cPickle`, `xrange`, and integer division) to be migrated automatically,
**So that** my boilerplate is converted without human intervention.

*Acceptance Criteria:*
1. A regex template engine must replace known standard library renames and syntax changes automatically.
2. The template engine must be idempotent (running it twice on the same codebase does not corrupt the output).
3. The converted output must be syntactically valid Python 3 code.

### Epic 3: Behavioral Verification
**As a** QA engineer,
**I want** the migrated code to be executed alongside the original legacy code using generated fixtures,
**So that** I am 100% confident that the new Python 3 function behaves identically to the old Python 2 function.

*Acceptance Criteria:*
1. The tool must spin up isolated `python:2.7-slim` and `python:3.12-slim` Docker containers.
2. The original and converted functions must be executed in their respective containers against matching sets of arguments (Hypothesis fixtures).
3. Output differences must be diffed using `DeepDiff`. If they match, the function is marked `pass`. If they drift, it is marked `clear_mismatch`.

### Epic 4: Pull Request Integration
**As a** repository maintainer,
**I want** the migration tool to surface ambiguous conversions directly on my Pull Requests,
**So that** I can review edge cases without having my PR blocked by hard failures.

*Acceptance Criteria:*
1. The tool must output a `build/summary.json` file.
2. The GitHub Action must parse the summary and inject a PR comment for any function marked `needs_review`.
3. The pipeline must remain green (exit code 0) for `needs_review` items, and only fail for explicit behavioral mismatches.
