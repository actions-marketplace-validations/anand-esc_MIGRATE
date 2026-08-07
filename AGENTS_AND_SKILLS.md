# Agents and Skills

This repository includes custom AI tooling configurations to assist with the complex task of migrating legacy codebases. These are located in the `.agents/` directory, adhering to the Antigravity architecture for customizations.

## Custom Skill: `py2-migrator`
**Location:** `.agents/skills/py2-migrator/SKILL.md`

This skill provides an AI assistant with the domain knowledge and exact workflows required to successfully use the `legacy-pyconvert` CLI tool. It prevents the AI from attempting ad-hoc manual migrations by enforcing a strict process:
1. Run the `legacy-pyconvert` equivalence checker.
2. Target only functions marked `needs_review`.
3. Test against the sandbox before proceeding.

## Custom Agent: `migration-specialist`
**Location:** `.agents/agents/migration_specialist.json`

This is a defined subagent role specifically tuned for deep-dive debugging of equivalence failures. When the main orchestrator agent encounters a `clear_mismatch` from the sandbox verifier, it can spawn this subagent and delegate the specific function to it. The `migration-specialist` is instructed to compare standard error traces from the `python:2.7-slim` and `python:3.12-slim` Docker containers to isolate syntax and behavioral drifts.
