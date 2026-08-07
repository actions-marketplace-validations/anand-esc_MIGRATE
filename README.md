# Legacy Python Equivalence Converter

A powerful, automated GitHub Action that safely migrates legacy Python 2 codebase to Python 3. It utilizes template engines for syntax migration and proves behavioral equivalence via strict, sandboxed diffing using isolated Docker containers.

## Features
- **Classification Engine**: Parses Python 2 syntax and intelligently routes it through the regex template engine or flags it for human/LLM review.
- **Template Engine**: Automatically translates common Python 2 idioms, octals, syntax, standard library imports to Python 3.
- **Robust Fixture Verification**: Executes both the original and converted code side-by-side in isolated Docker sandboxes (`python:2.7-slim` and `python:3.12-slim`) to definitively prove behavioral equivalence using strict assertions and `DeepDiff`.
- **Auto-Commit**: Automatically commits successfully migrated files back to your repository's `migrated/` directory.
- **PR Annotations**: Surfaces ambiguous or critic-flagged functions directly in your pull request as a summary comment for human review, without silently passing over them.

## Usage

Add this to your repository's workflow (e.g., `.github/workflows/migrate.yml`):

```yaml
name: Migrate Python 2 to 3

on:
  push:

jobs:
  run-migration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Equivalence Converter
        uses: anand-esc/MIGRATE@v1.0.0
        with:
          target-path: '.'
          fail-on-mismatch: 'true'
          auto-commit: 'true'
```

## Inputs

- `target-path` (Required): Path to Python 2 source within the repo (file or directory).
- `fail-on-mismatch` (Optional): Fail the job if any function comes back a clear mismatch. Default is `'true'`.
- `auto-commit` (Optional): Automatically commit the migrated files back to the repository. Default is `'true'`.
