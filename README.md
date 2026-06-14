# ODIN — Orchestrated Deductive Intelligence Network

ODIN is an **AGI-*like*** LLM agent-orchestration framework: it decomposes goals into
executable plans, delegates to specialized agents, **verifies** results through multiple
independent strategies, **persists memory** across sessions, and — over later phases —
**improves itself** through a bounded, verified, human-gated loop.

> ODIN is **not** a new foundation model. It is a reliable control layer built on top of
> existing frontier LLMs (Claude, GPT). The intelligence comes from the *loop, the
> verifier, the memory, and the safety bounds* — not from a bigger model.

A working **Phase 1** already exists in `zora-core/zora-core/odin/` (single reliable agent
with persistence, 75 passing tests). This repository is the home for the **full build-out**
described in [`docs/ROADMAP.md`](docs/ROADMAP.md).

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

## Status

This repo currently contains the **plan**. See [`docs/ROADMAP.md`](docs/ROADMAP.md)
for the full step-by-step build, including the self-improvement subsystem and the
GitHub integration design.

## License

TBD by the repo owner.
