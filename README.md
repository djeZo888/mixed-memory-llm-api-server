# Sova V1 closeout

**Sova V1 ended prematurely on 2 October 2026. Development continues in [Sova V2](https://github.com/djeZo888/SovaV2).** V1 produced useful components and some real working flows, but did not deliver the complete system requested by the user.

This branch, `docs/sova-v1-final-closeout-20261002`, is a documentation-only **review candidate**. Merge it into V1's default branch, `main`, only after human review. It contains curated retirement documents and the [retained licensing note](LICENSE.todo.md); it is not a runnable release, an installer, or permission to operate the former installation.

The last complete V1 source baseline is [commit `1f9bd99621d079f049d945dd1cc65bce96ae0c29`](https://github.com/djeZo888/mixed-memory-llm-api-server/commit/1f9bd99621d079f049d945dd1cc65bce96ae0c29), retained in this branch's ancestry. Historical code, reports, configuration and tests remain accessible at that commit. Removing them from the branch's current tree does not erase the Git history. Model assets and user data require their own preservation and migration decisions.

The final V1 report demonstrated a complete basic answer, continuation after a browser tab was closed, public file retrieval, and one manual native compaction with a successful follow-up. It did **not** qualify reliable research completion, image recognition, generation/editing, automatic large-context compaction, physical-PC sleep, or simultaneous operation of all required models. A native final response still sometimes arrived before the requested task was fulfilled. See the [postmortem](docs/POSTMORTEM.md) for evidence and limits.

- [Current backlog](TODO.md): four V2 foundation tasks, first-release gates, and later requirements.
- [User vision](docs/VISION.md): standing product direction, with latest decisions separated from older choices.
- [Postmortem](docs/POSTMORTEM.md): concrete failures, agent responsibility, and lessons.
- [Reuse inventory](docs/REUSE-INVENTORY.md): preserve, review, replace and defer decisions.
- [V2 design input](docs/V2-DESIGN-INPUT.md): small working units, configuration, protocols and tests.
- [VM reset record](docs/VM-RESET.md): preservation, reset outcome and limits.

Historical successful tests are evidence for their exact versions and scenarios, not automatic acceptance of V2. This closeout proposes no new runtime operation or deployment.
