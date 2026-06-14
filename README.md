# ODIN — Orchestrated Deductive Intelligence Network

ODIN is an **AGI-*like*** LLM agent-orchestration framework: it decomposes goals into
executable plans, delegates to specialized agents, **verifies** results through multiple
independent strategies, **persists memory** across sessions, and — over later phases —
**improves itself** through a bounded, verified, human-gated loop.

> ODIN is **not** a new foundation model. It is a reliable control layer built on top of
> existing frontier LLMs (Claude, GPT). The intelligence comes from the *loop, the
> verifier, the memory, and the safety bounds* — not from a bigger model.

The **Phase 1** implementation (single reliable agent with persistence) now lives here in
[`odin/`](odin/) — 78 passing tests, `ruff` + `mypy` clean. This repository is the home for
the **full build-out** described in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## The Pantheon (agents & subsystems)

| Component    | Role                                                        |
|--------------|-------------------------------------------------------------|
| **ODIN**     | Planner — decomposes goals into a Plan-DAG                   |
| **THOR**     | Executor — runs tools; never self-approves                  |
| **LOKI**     | Critic — adversarial, decorrelated review of proposals      |
| **FREYA**    | Renderer — produces the final cited answer                  |
| **MIMIR**    | Memory — working / episodic / semantic / procedural         |
| **HEIMDALL** | Safety — capabilities, approval gates, budget, injection    |
| **VERIFIER** | Verification engine — self-consistency, critic, grounding   |
| **MUNINN**   | Self-improvement (RSIP) — proposes & validates upgrades      |
| **BIFRÖST**  | GitHub engine — atomic, gated commits & PRs                 |

This is the *core* pantheon. The **full vision** — ~35 subsystems spanning world models
(YGGDRASIL), temporal/causal reasoning (NORNS), simulation (VÖLVA), formal verification
(MJÖLNIR), continual learning (IDUNN), multi-agent debate (FORSETI), containment
(FENRIR/GLEIPNIR), alignment (BALDR), and resilience (RAGNARÖK/EIR) — is catalogued, with
honest feasibility tiers, in [`docs/PANTHEON.md`](docs/PANTHEON.md).

## Core loop

```
Goal → ODIN (plan) → THOR (execute via tools) → LOKI (critique)
         ↕                    ↕                       ↕
       MIMIR ←────── HEIMDALL (gate) ──────→ VERIFIER
         ↓
       FREYA (render cited answer)
         ↓
       MUNINN (reflect → propose improvement → BIFRÖST PR, if enabled)
```

## Quick start

```bash
pip install -e ".[dev]"

# Run (set ANTHROPIC_API_KEY or OPENAI_API_KEY for a real LLM; omit for the offline FakeLLM)
export ANTHROPIC_API_KEY=your-key-here
odin run "research Python async patterns, compute timing benchmarks, summarize with sources"

odin memories          # view stored memories
odin rsip-demo         # watch one self-improvement (RSIP) cycle, fully offline
pytest tests/ -v       # run the test suite (109 tests)
```

See [`odin/README.md`](odin/README.md) for the Phase 1 component docs and
[`odin/ARCHITECTURE_DECISIONS.md`](odin/ARCHITECTURE_DECISIONS.md) for documented trade-offs.

## Status

- **Phase 1 — done:** single reliable agent with persistence (in [`odin/`](odin/), CI green).
- **Phase 4 (RSIP) core — done:** the **MUNINN** self-improvement engine ([`odin/improve/`](odin/improve/)),
  the **VÍGRÍÐR** benchmark, **BIFRÖST** PR publisher ([`odin/github/`](odin/github/)), and **HEIMDALL**
  self-modification caps (protected paths, diff-size cap, kill-switch). Bounded, verified, human-gated —
  MUNINN opens a PR, a human merges. Try `odin rsip-demo`.
- **Phase 2 hardening — done:** structured self-consistency (deterministic semantic similarity, no LLM
  judge call) and budget-through-LLM (`TrackedLLM` meters every reasoning call).
- **Next:** RSIP telemetry triggers, sandbox worktree, and one-command rollback.
- 109 tests, `ruff` + `mypy` clean.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full step-by-step build, including the
self-improvement subsystem and the GitHub integration design.

## License

TBD by the repo owner.
