Om — Parser & Classifier (Agent A)
•Builds the AST-based classifier: tags every function as template-matchable, LLM-needed, or unsupported/skip
•Builds the template library for known patterns (print statement, xrange → range, .iteritems() → .items(), etc.) — these convert for zero tokens
Owns: parser.py, classifier.py, templates/
Also: writes the classifier section of ARCHITECTURE.md
Needs from others: nothing to start — can begin immediately with sample legacy code
Gives to others: the classifier's output schema, needed by Suryansh — agree on this in the Day 1 morning sync

Suryansh — Converter & Critic (Agent B)
•Builds the LLM Converter: takes functions flagged complex and converts them to Python 3, one scoped prompt per function
•Builds the Critic: a review pass that catches leftover Py2 syntax or signature mismatches before the Verifier sees the output
•Tracks token usage — templates vs LLM calls — as a demo metric
Owns: converter.py, critic.py, prompt templates, debugging, ideation
Needs from others: the classifier's output format from Om, Day 1 morning sync

Pritam — Fixture Generator & Verifier (Agent C)
•Builds the Fixture Generator: deterministic per-function test inputs
•Builds the Verifier: runs fixtures in both containers, diffs outputs, implements the three-way pass/fail/ambiguous logic — the project's custom agent
•Sets up both Dockerfiles (Python 2 runtime, Python 3 runtime) and the plain, non-AI diff script
Owns: fixtures.py, verifier.py, both Dockerfiles, diff.py
Also: drafts AGENTS_AND_SKILLS.md
Needs from others: nothing to start — Docker setup and fixture logic can begin in parallel from hour one

Soumini — CLI, CI/CD, Docs & Demo (Agent D)
•Builds convert.py, the orchestration CLI — scaffolds with stubs on Day 1 before real modules exist, wires in real pieces as they land
•Sets up GitHub Actions: trivial green run committed Day 1 morning, real steps swapped in through Day 2
•Assembles ARCHITECTURE.md and writes AGENTS.md
•Picks the actual 10–15 functions from a real open-source Python 2 repo for the demo
•Packages the tool as a reusable GitHub Action and runs the final demo and pitch (see section 5)
Owns: convert.py, .github/workflows/, action.yml, ARCHITECTURE.md, AGENTS.md, demo repo selection
Needs from others: stub interfaces agreed in the Day 1 sync; real modules from all three by Day 2 morning for integration
