# GGFK Contributor Guide

GGFK is a bilingual school management and report-card system used by school
administrators, teachers, and parents. It is a real production system holding
sensitive school and family data, not a disposable demo. Protect that data and
preserve the school's established academic and access-control rules.

## Standing Documentation Rule

These rules apply to every change, including fixes and refactors:

- Every new file gets a module docstring or header comment explaining its
  purpose in plain language, using the format appropriate to that file type.
- Every new or changed public function gets a docstring or documentation
  comment explaining what it does, its inputs, its outputs, and any rule it
  enforces.
- Inline comments explain WHY, not WHAT. Always comment domain rules and
  security checks where they are enforced, including the Ministry grading
  chain, parent visibility, APPROVE versus ENVOYER, and passage thresholds.
  APPROVE publishes a bulletin to the parent portal; ENVOYER delivers a
  notification about an already-published bulletin.
- When behavior changes, update the comments describing it in the same change.
  An outdated comment counts as a bug.
- Use plain English that a developer new to this project can understand.

## Standing Workflow Rules

- Inspect first, report findings and a plan, then wait for approval before
  implementation.
- Reproduce bugs with a failing test before fixing them.
- Keep one job per ticket. Report bugs found during unrelated work; do not fix
  them in that same change.
- Agents never run Git operations or database migrations. The project owner
  handles these operations.
- Write needed migrations for review only; never apply them as an agent.
- Prefix test data with `ZZ-TEST-` and clean it up after testing.
- Any feature that filters, hides, or deletes data must list every existing
  read path that touches that data, with a test for each path.
- Never touch production, Render, Neon, or third-party services during
  development or testing. Use isolated local test data and mock external
  services.
