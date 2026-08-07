---
name: py2-migrator
description: A specialized skill for migrating legacy Python 2 code using the Legacy Python Equivalence Converter.
---

# Python 2 Migration Skill

This skill equips the agent with best practices for migrating Python 2 repositories to Python 3 using the `legacy-pyconvert` tool.

## Workflows

### 1. Running the Converter
When asked to migrate a repository, always use the automated CLI tool first before making manual edits:
```bash
legacy-pyconvert convert . --out build
```

### 2. Handling 'needs_review'
If the tool surfaces a function as `needs_review`:
- **Do not** manually edit the `migrated/` output directory.
- Instead, investigate the function in the original source code.
- Manually apply the required Python 3 fixes (e.g. LLM-required logic refactoring) to the original file.
- Re-run `legacy-pyconvert` to verify that the function now parses and passes the equivalence check.

### 3. Reviewing the Report
Always generate and review the GitHub-formatted report to summarize the migration:
```bash
legacy-pyconvert report --out build --format github
```
