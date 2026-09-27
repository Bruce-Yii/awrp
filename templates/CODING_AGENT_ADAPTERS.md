# Coding-agent adapters

One canonical Worker Contract: `protocol/WORKER-CONTRACT.md`. No protocol
forks. Each agent wires its own instruction surface to that contract.

## Codex

- Workspace `AGENTS.md` includes or links `templates/AGENTS_AWRP.md`.
- `AGENTS_AWRP.md` points to the canonical Worker Contract.

## Claude Code

- Project or global `CLAUDE.md` points to the workspace `AGENTS.md`, or directly
  to `templates/AGENTS_AWRP.md`.

## OpenCode

- Project or global instructions point to `templates/AGENTS_AWRP.md` and thus
  to the canonical Worker Contract.

## Rules for all adapters

- Adapters translate discovery, never semantics.
- On conflict, canonical protocol and history win.
- Keep adapters thin: link, do not copy.
- Contract edits happen once, in `protocol/WORKER-CONTRACT.md`.
