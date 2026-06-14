# The Ultimate ODIN Build Plan

A concrete, ordered, step-by-step plan to build ODIN from scaffold to a self-improving,
GitHub-connected agent system — using only current / near-future technology. No quantum
computing, no AGI hand-waving. The "self-improvement" is real but **bounded, verified, and
human-gated**.

**Guiding principle:** reliability lives in the *loop, the verifier, the memory, and the
safety bounds* — not in a bigger model. Build bottom-up so every layer is testable before
the next depends on it.

---

## Phase 0 — Foundations (repo + contracts)

> Goal: a typed, testable skeleton that everything else plugs into.

- [ ] **0.1** Repo scaffold: `odin/` package, `tests/`, `pyproject.toml` (Python 3.11+),
  `ruff` + `mypy` configured, `pytest`.
- [ ] **0.2** Typed contracts (Pydantic) — *build these first, everything passes them around*:
  `PlanNode`, `PlanDAG`, `MemoryRecord`, `VerdictRecord`, `Skill`, `BudgetState`,
  `ImprovementProposal` (new — for self-improvement).
- [ ] **0.3** Provider-agnostic **LLM adapter**: one interface over Anthropic + OpenAI, plus a
  **deterministic `FakeLLM`**. *The `FakeLLM` is the most important early decision* — it lets
  the entire loop be tested offline with zero cost and zero flakiness.
- [ ] **0.4** **Model router**: cheap (Haiku) vs frontier (Sonnet/Opus) selection = the
  practical version of "adaptive compute."
- [ ] **0.5** CI from day one: `ruff`, `mypy`, `pytest` on every PR (GitHub Actions).

**Exit criteria:** `pytest` green, `ruff`/`mypy` clean, `FakeLLM` round-trips a plan offline.

*(Phase 0–1 already exist in `zora-core/zora-core/odin/`. First step here is to migrate that
code in as the baseline — see "Step 1" in the Execution Checklist below.)*

---

## Phase 1 — Single reliable agent with persistence

> Goal: one agent that plans, executes, verifies, remembers — and never lies confidently.

- [ ] **1.1 Orchestration loop** (`core/orchestrator.py`):
  `plan → schedule → delegate → verify → commit/revise → reflect → consolidate`,
  with **bounded retries and budget checks at every stage** (the bounds are what stop runaway loops).
- [ ] **1.2 Verification layer** (`verify/`) — the single biggest reliability lever:
  - Self-consistency (re-derive independently, compare)
  - **LOKI** adversarial critic (decorrelated: different model family than the proposer)
  - Tool-grounding (execute code/math, compare to claimed output)
  - Verdict aggregation → accept / revise / abstain
- [ ] **1.3 MIMIR memory**: working (in-proc) + episodic (SQLite + vector store) + semantic graph,
  hybrid retrieval (dense + keyword), provenance on every record, **cross-session persistence**.
- [ ] **1.4 HEIMDALL safety**: per-agent capability matrix, risk-based approval gates,
  budget enforcement (tokens / calls / time / depth), injection detection, audit log.
  *Gated before tools run, not after.*
- [ ] **1.5 Tools**: sandboxed code interpreter, real web search (Tavily), tool registry gated by HEIMDALL.
- [ ] **1.6 Agents as thin roles**: ODIN (plan) / THOR (execute, never self-approves) /
  LOKI (critique) / FREYA (render cited answer).
- [ ] **1.7 CLI**: `odin run "<goal>"`, `odin memories`.

**Exit criteria:** end-to-end run on a real multi-step goal with citations, persisted memory,
enforced budget, and a verdict trail.

---

## Phase 2 — Hardening (close the honest shortcuts)

> Goal: make Phase 1 production-trustworthy. These map 1:1 to the documented Phase 1 limitations.

- [ ] **2.1 Structured verification** (highest value): replace "LLM judges LLM" self-consistency
  with structured output + semantic similarity, so the comparison can't silently be wrong.
- [ ] **2.2 Budget through LLM calls** (not just tools): wrap every adapter call in
  `record_llm_call()` → real token/cost caps instead of wall-clock approximation.
- [ ] **2.3 Container sandbox** for code execution (replace `preexec_fn` rlimits) → safe parallel exec.
- [ ] **2.4 DAG parallelism**: execute independent `PlanNode`s concurrently (the DAG already encodes deps).
- [ ] **2.5 ML-based injection detection** to replace hardcoded regex patterns.
- [ ] **2.6 Scalable backends**: optional Neo4j semantic graph; pluggable vector DB.

**Exit criteria:** parallel DAG execution, real cost accounting, container isolation, ≥90% test coverage.

---

## Phase 3 — Procedural memory & skills (the bridge to self-improvement)

> Goal: ODIN gets *better at recurring tasks over time* — the gateway to true self-improvement.

- [ ] **3.1 Skill extraction**: after a successful, verified run, distill the plan+tools into a reusable `Skill`.
- [ ] **3.2 Skill retrieval & auto-invocation**: match new goals to stored skills; reuse instead of re-deriving.
- [ ] **3.3 Skill scoring**: track success/cost per skill; prefer high-yield skills; retire bad ones.
- [ ] **3.4 Reflection memory**: store *why* runs failed, not just that they failed (post-mortems as memory).

**Exit criteria:** measurable drop in cost/latency on repeated task families; skills demonstrably reused.

---

## Phase 4 — Self-Improvement (RSIP via MUNINN) — *bounded, verified, human-gated*

> Goal: ODIN proposes improvements to **its own code, prompts, and skills**, validates them,
> and ships them through GitHub — **safely**.

**The non-negotiable safety model (read this first):**

```
MUNINN observes a weakness  →  proposes a change (ImprovementProposal)
        →  applies it on an ISOLATED branch (never main)
        →  runs the FULL test suite + benchmark eval in a SANDBOX
        →  LOKI critiques the diff (adversarial review)
        →  HEIMDALL checks scope/risk/budget caps
        →  BIFRÖST opens a PR  →  HUMAN approves merge
```

- [ ] **4.1 Improvement triggers**: detect weaknesses from telemetry — repeated failures on a task
  family, low verifier confidence, high cost, slow nodes, recurring error signatures.
- [ ] **4.2 `ImprovementProposal` contract**: `{target_file, rationale, diff, expected_metric_delta, risk}`.
- [ ] **4.3 Candidate generation**: a frontier LLM proposes a *minimal, scoped* diff (prompt tweak,
  new skill, new tool, refactor). **No rewriting the safety layer (HEIMDALL) without explicit human sign-off.**
- [ ] **4.4 Self-evaluation harness** (the heart of RSIP): a fixed **benchmark suite** of held-out tasks
  with known-good outcomes. A proposal is accepted **only if** it (a) keeps all tests green and
  (b) improves a target metric (accuracy / cost / latency) **without regressing others**.
  *This eval set is what prevents "self-improvement" from becoming self-degradation.*
- [ ] **4.5 Isolation**: every candidate runs on its own git branch in a sandboxed worktree;
  changes never touch the running process or `main`.
- [ ] **4.6 Adversarial gate**: LOKI reviews the diff for correctness, scope creep, and reward-hacking.
- [ ] **4.7 HEIMDALL caps on self-modification**: max diff size, forbidden paths (safety/budget code),
  per-cycle budget, and a kill-switch.
- [ ] **4.8 BIFRÖST PR**: open a PR with the proposal, metric deltas, and eval report attached.
- [ ] **4.9 Human-in-the-loop merge** (default ON): a human approves. *Auto-merge stays OFF until the
  eval harness + rollback are battle-tested; even then it's opt-in and limited to low-risk paths.*
- [ ] **4.10 Rollback**: every self-change is a revertible commit; one command restores the last-good state.

**Exit criteria:** ODIN opens a real PR that measurably improves a benchmark metric, passes CI + LOKI,
and is merged by a human — fully logged and reversible.

---

## Phase 5 — Multi-agent autonomy & continuous operation

> Goal: ODIN runs as a service, coordinating multiple agents on long-horizon goals.

- [ ] **5.1** Durable, resumable jobs (checkpoint state; survive restarts).
- [ ] **5.2** Agent-to-agent delegation across parallel sub-DAGs with shared MIMIR.
- [ ] **5.3** Scheduler/daemon mode: queue goals, run on schedule, report.
- [ ] **5.4** Live research agents (web/RAG) feeding fresh, cited context into memory.
- [ ] **5.5** Observability dashboard: plan DAGs, verdicts, budget, self-improvement history.

**Exit criteria:** ODIN completes a multi-hour, multi-goal workload unattended, within budget, with full audit trail.

---

## Phase 6 — Multi-modal & continuous adaptation

> Goal: extend beyond text; keep knowledge fresh without full retrains.

- [ ] **6.1** Multi-modal tools (image/audio/structured-table understanding via provider APIs).
- [ ] **6.2** Continuous knowledge refresh through MIMIR (retrieval-first) instead of model retrains.
- [ ] **6.3** Calibration: ODIN reports reliable confidence and abstains when evidence is weak.

---

## GitHub Integration (BIFRÖST) — "connect it to my GitHub"

> Goal: ODIN reads from and ships to GitHub safely. This is how the system "connects to your GitHub."

**Setup steps:**

- [ ] **G.1** This repo (`THEZORACORE/ODIN`) is the home; the plan lands here first (this PR).
- [ ] **G.2** Migrate Phase 1 code from `zora-core/zora-core/odin/` into this repo as the baseline.
- [ ] **G.3** GitHub App / fine-grained PAT scoped to **this repo only**, least-privilege
  (contents: read/write, pull_requests: write). Stored as a secret — never in code.
- [ ] **G.4** **BIFRÖST engine**: a thin, atomic git layer — create branch, commit signed changes,
  push, open PR via the GitHub API. **Never force-pushes; never pushes to `main`.**
- [ ] **G.5** GitHub Actions CI: `ruff` + `mypy` + `pytest` + the **Phase 4 benchmark eval** on every PR.
- [ ] **G.6** Branch protection on `main`: required CI + required human review (this is what makes
  autonomous self-improvement safe).
- [ ] **G.7** Self-improvement PRs (Phase 4) flow through BIFRÖST → CI + LOKI → human merge.

**How self-improvement + GitHub fit together:**

```
ODIN runs  →  MUNINN detects weakness  →  proposes diff on a new branch
   →  sandbox: full tests + benchmark eval  →  LOKI adversarial review  →  HEIMDALL caps
   →  BIFRÖST opens PR  →  GitHub Actions CI  →  HUMAN approves  →  merge  →  ODIN reloads
   →  (always reversible via git revert)
```

---

## Execution Checklist (the order I'll actually do it in)

1. **Bootstrap this repo** with the plan (this PR).
2. **Migrate Phase 1** code from `zora-core/zora-core/odin/` → `THEZORACORE/ODIN` as the baseline; wire up CI.
3. **Phase 2 hardening**, starting with **structured verification** and **budget-through-LLM** (highest value, lowest risk).
4. **Phase 3 skills** — extraction + retrieval (the bridge to self-improvement).
5. **Phase 4 RSIP/MUNINN** — build the **benchmark eval harness FIRST**, then candidate generation, then BIFRÖST PR flow, with human-gated merge + rollback.
6. **Phase 5 autonomy** — durable jobs, daemon, observability.
7. **Phase 6 multi-modal + calibration.**

## Definition of "done" for ODIN being "the pinnacle"

- Every answer is **grounded, cited, and verified** by an independent critic.
- **Budgets are hard** (tokens/cost/time/depth) and enforced everywhere.
- ODIN **remembers and reuses** what it learns across sessions.
- ODIN can **improve its own code** via PRs that *provably* raise a benchmark metric — and every
  such change is reviewed by a human and reversible.
- The safety layer (HEIMDALL) is the one thing ODIN **cannot silently rewrite**.
