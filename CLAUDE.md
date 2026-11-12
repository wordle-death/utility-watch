# utility-watch: working rules

What this is: collectors and analysis for how often U.S. cities lose power and safe water, how many households it reaches, for how long, and what it costs. The scope is in the project's "Utility Impact Tracker Scope" doc; the stack follows the owner's stack.md (free first, $5 a month ceiling, no recurring cost without approval).

## Before merging

1. Tests pass: `python -m unittest discover -s tests -t .`
2. The live feed check on the branch ran, and its job result was read (it does not fail the run).
3. **Independent review.** Any change to logic or to how a number is calculated is reviewed by a separate agent that did not write it, before merge. Give the reviewer the diff and what the code is for, not the author's reasoning. Fix or answer every finding. Docs and config-only changes skip review. The owner has given standing approval to spawn review agents.
4. Say in the pull request what was checked and what was not.

## Numbers

- Every published number links to its source and says whether it was measured or estimated.
- Uncertain steps are flagged on the record (see `flags` in `advisory_timeline.json`), never silently resolved.
- When a method changes a headline figure, check the largest cases by hand against the source documents.

## Data jobs

- Collectors use only the Python standard library. The national job may use pandas.
- A feed that returns something unexpected is a failed run, not "no outages."
- Scheduled jobs commit to `main` through `scripts/commit_data.sh`.
