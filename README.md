# Unladen Velocity

a Python tool for web-based visualization of performance benchmarks

## Quickstart

```sh
make test    # fast unit tests
make lint    # static checks
make fmt     # auto-format
make verify  # full gate; what the agent runs before claiming done
```

## AI coding agents

This repository follows the **agent-agnostic harness** convention:

- `AGENTS.md` is the canonical instruction file for every agent
  (Codex, OpenCode, Cursor, Amp, Factory, Gemini CLI, Copilot, …).
- `CLAUDE.md` is a one-line import of `AGENTS.md` plus Claude-Code-only
  stanzas (skills, subagents, slash commands, hooks).
- Shared agent assets (skills, subagents, and slash commands) live under
  `.agents/` and are symlinked into `.claude/` and `.opencode/`.
- Per-feature specs go under `specs/<YYYY-MM>-<slug>/`.
- Architecture decisions are in `docs/adr/` (Michael Nygard format, append-only).

See `AGENTS.md` for the full conventions.

## License

BSD-3-Clause
