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
odin skills            # list learned procedural skills
odin skills-retire ID  # retire a bad skill so it stops being suggested
odin queue "<goal>"    # add a goal to the job queue
odin daemon            # run as a daemon, processing queued jobs
odin jobs              # show job queue and history
odin cancel-job ID     # cancel a queued job
odin research "<topic>" # research a topic, store cited findings in MIMIR
odin history           # show run history / audit trail
odin stats             # show aggregate system statistics
odin rsip-demo         # watch one self-improvement (RSIP) cycle, fully offline
odin rsip-triggers     # show telemetry-derived improvement triggers (offline)
odin rsip "<weakness>" # LIVE cycle: sandbox-test a candidate + open a real PR
odin rollback          # safely revert the last self-improvement commit
pytest tests/ -v       # run the test suite (215 tests)
```

See [`odin/README.md`](odin/README.md) for the Phase 1 component docs and
[`odin/ARCHITECTURE_DECISIONS.md`](odin/ARCHITECTURE_DECISIONS.md) for documented trade-offs.

## Status

- **Phase 1 — done:** single reliable agent with persistence (in [`odin/`](odin/), CI green).
- **Phase 4 (RSIP) — done:** the **MUNINN** self-improvement engine ([`odin/improve/`](odin/improve/)),
  the **VÍGRÍÐR** benchmark, **BIFRÖST** PR publisher ([`odin/github/`](odin/github/)), and **HEIMDALL**
  self-modification caps (protected paths, diff-size cap, kill-switch). Now also telemetry-driven
  improvement triggers, sandboxed git-worktree isolation for candidate testing, and one-command
  rollback. Bounded, verified, human-gated — MUNINN opens a PR, a human merges.
- **Phase 3 (skills) — done:** procedural memory ([`odin/skills/`](odin/skills/)). Successful runs are
  auto-distilled into reusable `Skill`s stored in a SQLite-backed `SkillStore`; the planner retrieves
  matching skills and reuses proven procedures. Failed runs produce reflection post-mortems.
  Skill scoring (success rate, cost, latency) + retirement via `odin skills-retire`.
- **Phase 2 hardening — done:** structured self-consistency, budget-through-LLM, DAG parallelism,
  container sandbox ([`odin/tools/sandbox.py`](odin/tools/sandbox.py) — Process/Docker/Mock),
  ML injection detection ([`odin/safety/injection.py`](odin/safety/injection.py) — TF-IDF classifier),
  and pluggable backends ([`odin/memory/backends.py`](odin/memory/backends.py) — Neo4j graph + vector DB).
- **Phase 5 (autonomy) — done:** durable, resumable jobs ([`odin/jobs/`](odin/jobs/)),
  agent-to-agent delegation with parent↔child tracking, scheduler/daemon mode,
  live research agents (HUGINN/MUNINN — [`odin/agents/research.py`](odin/agents/research.py)),
  and observability (HLIDSKJALF — [`odin/observe/`](odin/observe/)) with run history and stats.
  `odin queue` / `odin daemon` / `odin jobs` / `odin research` / `odin history` / `odin stats`.
- **Next:** Phases 7–12 (AGI-approaching layer: world model, multi-agent debate, formal guarantees).
- 215 tests, `ruff` + `mypy` clean.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full step-by-step build, including the
self-improvement subsystem and the GitHub integration design.

## License

TBD by the repo owner.
