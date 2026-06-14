# ODIN Demo — Phase 1

## Running the Demo

```bash
# Install
pip install -e ".[dev]"

# Option 1: With real LLM (set API key)
export ANTHROPIC_API_KEY=your-key
odin run "Calculate the first 10 Fibonacci numbers, verify the result, and explain the pattern"

# Option 2: FakeLLM demo mode (no API key needed)
odin run "Calculate 6 times 7"
```

## What Happens

When you run `odin run "<goal>"`, the system:

1. **ODIN plans** — Decomposes the goal into a Plan-DAG
2. **THOR executes** — Each step runs through tools (code interpreter, web search)
3. **HEIMDALL gates** — Every tool call is checked for capability, risk, budget, injection
4. **Verifier checks** — Self-consistency, LOKI critic, tool-grounding
5. **Commit or retry** — Verified results are committed; failures trigger bounded retries
6. **MIMIR reflects** — Episodic memory stored with provenance
7. **FREYA renders** — Final cited answer presented

## Example Session (FakeLLM)

```
$ odin run "Calculate 6 times 7"

ODIN starting session a1b2c3d4
Goal: Calculate 6 times 7

[dim]No API key found — using FakeLLM (demo mode)[/dim]

╭──── ODIN — Orchestration Result ────╮
│ Goal: Calculate 6 times 7           │
│ Status: SUCCESS                     │
│ Session: a1b2c3d4                   │
╰─────────────────────────────────────╯

    Plan Execution
┌────────┬────────────────────┬────────┬─────────┐
│ Step   │ Goal               │ Status │ Retries │
├────────┼────────────────────┼────────┼─────────┤
│ step_1 │ Calculate 6*7      │   ✓    │    0    │
└────────┴────────────────────┴────────┴─────────┘

    Verification Summary
┌──────────────────┬─────────┬────────────┐
│ Method           │ Outcome │ Confidence │
├──────────────────┼─────────┼────────────┤
│ self_consistency │  PASS   │    70%     │
│ critic           │  PASS   │    70%     │
└──────────────────┴─────────┴────────────┘

Budget: 234/100000 tokens, 7/50 LLM calls, 0/100 tool calls

╭──── Final Answer ────╮
│ The answer is 42.    │
╰──────────────────────╯
```

## Memory Persistence

```bash
# Run 1
odin run "Learn that the speed of light is 299792458 m/s" --session-id sess1

# Run 2 — memories persist
odin memories

# Shows:
# ┌──────────┬──────────┬─────────────────────────────────────┬─────────┐
# │ ID       │ Type     │ Content                             │ Session │
# ├──────────┼──────────┼─────────────────────────────────────┼─────────┤
# │ a1b2c3d4 │ episodic │ Goal: Learn that the speed of li... │ sess1   │
# └──────────┴──────────┴─────────────────────────────────────┴─────────┘
```

## Test Suite

```bash
$ pytest tests/ -v

# 75 tests covering:
# - Schema validation (PlanDAG, BudgetState, MemoryRecord)
# - HEIMDALL (injection detection, budget enforcement, capabilities, approval gates)
# - LLM adapter (FakeLLM, model router)
# - Memory (working, episodic, cross-session persistence, semantic graph, compression)
# - Verification (self-consistency, critic, tool-grounding, aggregation)
# - Tools (code interpreter sandbox, web search, registry)
# - Orchestrator (happy path, failed verification→revise, budget exhaustion, cross-session)
```

## Key Tests

| Test | Proves |
|------|--------|
| `test_gate_blocks_injected_arguments` | HEIMDALL blocks injection in tool args |
| `test_stops_on_budget_exhaustion` | Orchestrator halts when budget exhausted |
| `test_retry_on_verification_failure` | Failed verify triggers bounded retry |
| `test_persistence_across_sessions` | MIMIR memories survive close/reopen |
| `test_odin_cannot_use_code_interpreter` | Separation of duties enforced |
| `test_code_matches` / `test_code_mismatch` | Tool-grounding verification works |
