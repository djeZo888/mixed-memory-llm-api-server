# CONTRIBUTING.md

## Workflow

- Use feature branches.
- Do not push directly to `main`.
- Keep each change milestone-scoped.
- Run checks and update the relevant report before commit.
- Run a local secret scan before every push.

## Safety

- Do not mutate disks without the approved milestone dry-run.
- Do not download models before `/data` is mounted and verified.
- Do not install packages unless the active milestone explicitly calls for it.
- Do not commit real secrets or local machine state.

## Documentation Style

Prefer exact operational instructions, verifiable invariants, and failure conditions. Avoid host-specific secrets or private infrastructure details.
