# ODIN — Orchestrated Deductive Intelligence Network

**Phase 1: Single reliable agent with persistence.**

ODIN is an AGI-*like* LLM agent-orchestration framework that decomposes goals into
executable plans, delegates to specialized agents, verifies results through multiple
strategies, and persists memory across sessions.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run (set ANTHROPIC_API_KEY or OPENAI_API_KEY for real LLM; omit for FakeLLM demo)
export ANTHROPIC_API_KEY=your-key-here
odin run "research Python async patterns, compute timing benchmarks, summarize with sources"

# View stored memories
odin memories

# Run tests
pytest tests/ -v
```

## Architecture

```
Goal → ODIN (plan) → THOR (execute via tools) → LOKI (critique)
         ↕                    ↕                       ↕
       MIMIR ←────── HEIMDALL (gate) ──────→ VERIFIER
         ↓
       FREYA (render cited answer)
```

### Core Loop (§4.4)

```
plan → schedule → delegate → verify → commit/revise → reflect → consolidate
```

1. **PLAN** — ODIN decomposes goal into a Plan-DAG of PlanNodes
2. **SCHEDULE** — Topological ordering from DAG dependencies
3. **DELEGATE** — THOR executes each ready node using tools (via HEIMDALL)
4. **VERIFY** — Self-consistency + LOKI critic + tool-grounding
5. **COMMIT/REVISE** — Accept verified results or retry (bounded)
6. **REFLECT** — Store episodic memory with provenance
7. **CONSOLIDATE** — FREYA renders final cited answer

### Components

| Component | Role | Module |
|-----------|------|--------|
| **ODIN** | Planner — decomposes goals into Plan-DAGs | `odin/agents/odin_planner.py` |
| **THOR** | Executor — runs tools, never self-approves | `odin/agents/thor_executor.py` |
| **LOKI** | Critic — adversarial review of proposals | `odin/agents/loki_critic.py` |
| **FREYA** | Renderer — produces cited final output | `odin/agents/freya_renderer.py` |
| **MIMIR** | Memory — working/episodic/semantic/procedural | `odin/memory/mimir.py` |
| **HEIMDALL** | Safety — gates, capabilities, budget, injection | `odin/safety/heimdall.py` |
| **Verifier** | Verification engine (3 strategies) | `odin/verify/verifier.py` |
| **Orchestrator** | The full loop, wiring all components | `odin/core/orchestrator.py` |

### Schemas (§4.2)

All inter-agent messages use pydantic models (`odin/schemas/common.py`):

- `PlanNode` / `PlanDAG` — task decomposition
- `MemoryRecord` — with `Provenance` attached
- `VerdictRecord` — verification outcomes
- `Skill` — procedural memory (Phase 1 stub)
- `BudgetState` — resource tracking with hard limits
- `ToolRequest` / `ToolResult` — tool call protocol
- `AgentMessage` — inter-agent communication

### Memory (MIMIR)

| Layer | Backend | Status |
|-------|---------|--------|
| Working | In-process dict | Live |
| Episodic | SQLite + ChromaDB (dense) | Live |
| Semantic | NetworkX graph | Live |
| Procedural | Skill model (stored) | Stub interface |

Hybrid retrieval: dense vector (Chroma) + keyword (FTS5) with score fusion.
Recursive summarization/compression via LLM.
All records carry provenance (`source_type`, `source_id`, `timestamp`, `confidence`).

### Tools

| Tool | Risk | Status |
|------|------|--------|
| `code_interpreter` | MEDIUM | Live (sandboxed subprocess, resource-limited) |
| `web_search` | LOW | Live (pluggable adapter, mock for tests) |

All tool calls route through HEIMDALL's `gate()`.

### Safety (HEIMDALL)

- **Capability matrix** — each agent can only use authorized tools
- **Approval gates** — HIGH/IRREVERSIBLE actions require approval
- **Budget enforcement** — tokens, LLM calls, tool calls, wall-clock all capped
- **Injection detection** — 10 regex patterns for common prompt-injection attempts
- **Audit log** — every gate decision recorded

## Mitigated vs Solved vs Deferred (§2)

| Concern | Status | Detail |
|---------|--------|--------|
| Generation fallibility | **Solved** | Every output verified (self-consistency + critic + tool-grounding) before commit |
| Prompt injection | **Mitigated** | Regex-based detection on all external content; not ML-based, so adversarial evasion possible |
| Budget runaway | **Solved** | Hard caps on tokens, calls, time, recursion depth; checked at every loop iteration |
| Hallucination | **Mitigated** | Tool-grounding for code/math, critic review for reasoning; LLM claims still unverifiable for novel facts |
| Separation of duties | **Solved** | Planner/executor/critic/gatekeeper are distinct components with distinct authority |
| Memory persistence | **Solved** | SQLite + Chroma on disk, graph serialized; cross-session retrieval tested |
| Provenance | **Solved** | Every MemoryRecord carries Provenance list |
| Multi-agent parallelism | **Deferred** | Phase 2: DAG parallelism for THOR sub-tasks |
| Reflexion / skill library | **Deferred** | Phase 3: auto-skill extraction from successful runs |
| Neo4j semantic graph | **Deferred** | Phase 1 uses NetworkX; Neo4j adapter in Phase 2+ |

## Development

```bash
# Lint
ruff check odin/ tests/

# Type check
mypy odin/ --ignore-missing-imports

# Test
pytest tests/ -v

# Full check
ruff check odin/ tests/ && mypy odin/ --ignore-missing-imports && pytest tests/ -v
```

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | No* | Falls back to OpenAI or FakeLLM |
| `OPENAI_API_KEY` | No* | Falls back to FakeLLM |

*At least one API key required for production use. FakeLLM works for testing/demos.

## Project Structure

```
odin/
  core/        # orchestrator
  agents/      # odin, thor, freya, loki
  memory/      # MIMIR: working/episodic/semantic + retrieval/compression
  tools/       # sandbox, search, function-calling registry
  verify/      # self-consistency, critic, verdict records
  schemas/     # PlanNode, MemoryRecord, Skill, VerdictRecord (pydantic)
  routing/     # LLM adapter (Anthropic/OpenAI/FakeLLM), model router
  safety/      # HEIMDALL gates, capability, budget, injection guard
  cli/         # `odin run "<goal>"` entrypoint
tests/         # 75 tests covering loop, memory, verify, safety
```
