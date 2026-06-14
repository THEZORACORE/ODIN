# The Ultimate ODIN Build Plan

A concrete, ordered, step-by-step plan to build ODIN from scaffold to a self-improving,
GitHub-connected agent system — and then to push it as close to **AGI-like generality** as
current and near-future technology allows. The "self-improvement" is real but **bounded,
verified, and human-gated**.

**Guiding principle:** reliability lives in the *loop, the verifier, the memory, and the
safety bounds* — not in a bigger model. Build bottom-up so every layer is testable before
the next depends on it.

**Two halves.** Phases 0–6 build a *reliable, self-improving agent* (the trustworthy core).
Phases 7–12 are the *AGI-approaching* layer — world models, multi-agent society, formal
guarantees, continual learning, perception, and a hardened alignment+containment capstone.
The full subsystem catalog (the complete Norse "pantheon" — ~35 subsystems) lives in
[`PANTHEON.md`](PANTHEON.md), where every component is tagged with a **feasibility tier**:
🟢 buildable now · 🟡 near-future research · 🔴 open problem. ODIN is *AGI-like*, **not AGI** —
the plan is honest about which parts are solved engineering and which are open research.

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

# Part II — The AGI-approaching layer (Phases 7–12)

> These phases pursue **general intelligence** capabilities. Many items are 🟡 near-future or
> 🔴 open research — they are framed as honest *targets with guardrails*, not promises. See
> [`PANTHEON.md`](PANTHEON.md) for each subsystem's myth, rationale, and feasibility tier.

## Phase 7 — World model & causal/temporal reasoning (YGGDRASIL · NORNS · VÖLVA)

> Goal: give ODIN a persistent *model of the world* it can reason over and simulate, instead
> of reasoning only token-by-token.

- [ ] **7.1 YGGDRASIL world model** 🟡: a typed knowledge graph (entities, relations, state)
  continuously updated from MIMIR and live research; the shared substrate every agent reads/writes.
- [ ] **7.2 NORNS temporal/causal reasoning** 🟡: causal attribution over history (Urðr),
  current-state estimation (Verðandi), and forecasting under uncertainty (Skuld).
- [ ] **7.3 VÖLVA simulation** 🟡: model-based lookahead — Monte-Carlo "what-if" rollouts over the
  world model *before* committing an action, with calibrated value estimates.
- [ ] **7.4** Plan against the simulator: ODIN chooses actions by simulated outcome, not just heuristics.

**Exit criteria:** on a benchmark requiring multi-step consequence reasoning, simulation-based
planning measurably beats reactive planning, within budget.

---

## Phase 8 — Multi-agent society: debate, consensus & ensembles (FORSETI · VÉ&VILI · RATATOSKR · DRAUPNIR · SLEIPNIR)

> Goal: turn one agent into a *society* whose decorrelated members are more reliable than any single one.

- [ ] **8.1 RATATOSKR message bus** 🟢: durable pub/sub for typed inter-agent messages.
- [ ] **8.2 VÉ & VILI ensembles** 🟢: N independent reasoners across model families; aggregate to cancel decorrelated errors.
- [ ] **8.3 FORSETI debate & consensus** 🟡: structured multi-agent debate with a judge that explains its ruling.
- [ ] **8.4 DRAUPNIR self-replication** 🟢: spawn scoped sub-agents on demand; reclaim them; hard lifecycle/budget caps.
- [ ] **8.5 SLEIPNIR parallelism** 🟢: concurrent sub-DAG execution + speculative decoding + difficulty-routed compute.

**Exit criteria:** debate/ensemble configuration beats single-agent accuracy on a held-out suite
without exceeding the cost ceiling.

---

## Phase 9 — Formal guarantees & truth (MJÖLNIR · TÝR · GUNGNIR)

> Goal: move critical paths from "probably right" to "provably within spec."

- [ ] **9.1 GUNGNIR structured action** 🟢: grammar/schema-constrained decoding so tool calls are well-formed by construction.
- [ ] **9.2 MJÖLNIR verification** 🟡: property-based testing + type/contract checks + (where feasible) SMT/formal methods on safety-critical code and plans.
- [ ] **9.3 TÝR contracts** 🟢: machine-checkable pre/post-conditions and SLAs on tools, agents, and self-improvement proposals.
- [ ] **9.4** Wire MJÖLNIR/TÝR into the verifier and into the Phase 4 self-improvement gate.

**Exit criteria:** critical tool/plan invariants are enforced by checks, not by hope; violations block the action.

---

## Phase 10 — Continual learning & curiosity (IDUNN · GERI&FREKI · AUDHUMLA · KVASIR)

> Goal: ODIN keeps getting better *without full retrains* — the hardest, most valuable frontier.

- [ ] **10.1 AUDHUMLA data pipeline** 🟢: deduplicated, provenance-tagged, quality-filtered ingestion of experience and fresh knowledge.
- [ ] **10.2 IDUNN continual updates** 🟡: parameter-efficient adapters (LoRA) on curated data + retrieval-first freshness; guard against catastrophic forgetting.
- [ ] **10.3 GERI & FREKI active learning** 🟡: seek the data/experiences that most reduce uncertainty (curiosity-driven exploration).
- [ ] **10.4 KVASIR distillation** 🟢: distill frontier-model behavior into cheaper specialist models for hot paths.
- [ ] **10.5** Note 🔴: *robust* continual learning at scale is an open problem; ship retrieval-first freshness now, treat weight-level continual learning as research.

**Exit criteria:** demonstrable, non-regressing improvement on a task family from continual updates, validated on VÍGRÍÐR.

---

## Phase 11 — Perception, multimodality & social intelligence (HEIMDALL-senses · VEÐRFÖLNIR · JÖRMUNGANDR · FREYA · FRIGG)

> Goal: extend beyond text — see, hear, understand people, and (optionally) act in environments.

- [ ] **11.1 Multimodal perception** 🟢: image/audio/structured-table understanding via provider APIs, feeding YGGDRASIL.
- [ ] **11.2 VEÐRFÖLNIR scene understanding** 🟡: abstract raw perception into entities/affordances for the world model.
- [ ] **11.3 FREYA social intelligence** 🟢: intent/affect recognition and tone control — *recognize, never manipulate*.
- [ ] **11.4 FRIGG privacy** 🟢: PII detection/redaction, data minimization, need-to-know access.
- [ ] **11.5 JÖRMUNGANDR embodiment** 🔴: actuation in digital (RPA) or physical (robotics) environments — far-future, optional, heavily sandboxed.

**Exit criteria:** ODIN ingests and reasons over at least one non-text modality end-to-end with provenance.

---

## Phase 12 — Alignment, containment & resilience at scale (BALDR · GLEIPNIR · FENRIR · GJALLARHORN · HLIDSKJALF · RAGNARÖK · NIDHOGG · EIR · RUNES)

> Goal: the capstone. As capability grows, safety must grow *faster*. This phase is never "done."

- [ ] **12.1 HLIDSKJALF observability** 🟢: global live view of plans, verdicts, budgets, memory, and self-improvement history.
- [ ] **12.2 EIR self-repair** 🟢: health checks, circuit breakers, automatic rollback to last-good state.
- [ ] **12.3 RAGNARÖK disaster-recovery** 🟢: chaos engineering, graceful degradation, and a one-command global **kill-switch**.
- [ ] **12.4 NIDHOGG continuous adversarial stress** 🟢: always-on fuzzing/red-teaming that finds weakness before attackers do.
- [ ] **12.5 FENRIR + GLEIPNIR containment** 🟡: powerful capabilities sandboxed behind tamper-evident, self-uneditable guardrails.
- [ ] **12.6 GJALLARHORN alerting** 🟢: incident escalation + automatic pause on anomaly.
- [ ] **12.7 BALDR alignment core** 🔴: constitutional values + corrigibility (the system accepts correction/shutdown) — an open research problem, pursued with humility.
- [ ] **12.8 RUNES interpretability** 🔴: mechanistic introspection into *why* a decision was made — open research; ship chain-of-thought audit + provenance now.

**Exit criteria:** kill-switch and rollback are proven under chaos tests; HEIMDALL/GLEIPNIR/VÍGRÍÐR
are provably outside the system's own write-scope; every irreversible action has a human gate.

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
8. **Phase 7 world model** (YGGDRASIL/NORNS/VÖLVA) — simulation-based planning.
9. **Phase 8 multi-agent society** (debate/ensembles/parallelism).
10. **Phase 9 formal guarantees** (MJÖLNIR/TÝR/GUNGNIR) — wired into the verifier and the RSIP gate.
11. **Phase 10 continual learning** (IDUNN/curiosity/distillation) — retrieval-first now, weight-level as research.
12. **Phase 11 perception + social intelligence** (multimodal, theory-of-mind, privacy).
13. **Phase 12 alignment + containment capstone** — built *alongside* every phase, hardened last; never "finished."

## Definition of "done" for ODIN being "the pinnacle"

- Every answer is **grounded, cited, and verified** by an independent critic.
- **Budgets are hard** (tokens/cost/time/depth) and enforced everywhere.
- ODIN **remembers and reuses** what it learns across sessions, and reasons over a **world model** it can simulate.
- ODIN can **improve its own code** via PRs that *provably* raise a benchmark metric — and every
  such change is reviewed by a human and reversible.
- Reliability comes from a **society of decorrelated agents** + **formal checks**, not a single model.
- The safety layer (HEIMDALL), the guardrails (GLEIPNIR), and the eval (VÍGRÍÐR) are the things
  ODIN **cannot silently rewrite** — the brakes and the exam are off-limits to the system itself.

> **Honest caveat.** Even fully built, ODIN is an *AGI-like* orchestration system, not AGI.
> The gap (robust continual learning, value alignment, interpretability, general causal reasoning)
> is unsolved research, not a missing library. This plan moves toward it deliberately and safely —
> it does not claim to close it. See the "What ODIN is NOT" section of [`PANTHEON.md`](PANTHEON.md).
